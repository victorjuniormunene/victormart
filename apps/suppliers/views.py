from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models import Avg, Count
from .models import Supplier, Product as SupplierProduct, SupplierSubscriptionPayment
from apps.products.models import Product
from apps.products.entitlements import (
    product_post_limit,
    product_posts_in_last_week,
    record_customer_product_view,
    shopper_visible_products,
)
from apps.products.permissions import manageable_products
from .forms import ProductForm, SupplierOrderForm, SupplierProfileForm
from apps.orders.forms import OrderForm
from apps.orders.models import Order
from django.contrib import messages
from django.shortcuts import HttpResponse
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import json
from urllib.parse import quote, urlsplit, urlunsplit
from decimal import Decimal, InvalidOperation

def product_list(request):
    retail_categories = dict(Product.CATEGORY_CHOICES)
    products = shopper_visible_products().annotate(
        review_average=Avg('reviews__rating'),
        review_count=Count('reviews'),
    )
    selected_category = request.GET.get('category', '')
    if selected_category in retail_categories:
        products = products.filter(category=selected_category)
    return render(request, 'products/product_list.html', {
        'products': products,
        'retail_categories': Product.CATEGORY_CHOICES,
        'selected_category': selected_category,
    })

@login_required
def product_create(request):
    if not getattr(request.user, 'is_supplier', False):
        messages.error(request, 'Only suppliers can create products.')
        return redirect('accounts:dashboard')

    supplier, _ = Supplier.objects.get_or_create(
        user=request.user,
        defaults={'company_name': request.user.username},
    )
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
                post_limit = product_post_limit(supplier)
                post_count = product_posts_in_last_week(supplier)
                if post_count >= post_limit:
                    messages.error(
                        request,
                        f'Your current plan allows {post_limit} new product posts per rolling 7-day period. '
                        'Upgrade to premium or try again when your quota resets.',
                    )
                    return redirect('dashboard:supplier_dashboard')
                product = form.save(commit=False)
                product.supplier = supplier
                product.save()
            messages.success(request, 'Product created successfully.')
            return redirect('suppliers:product_list')
    else:
        form = ProductForm()
    return render(request, 'suppliers/product_form.html', {'form': form})

@login_required
def product_update(request, pk):
    product = get_object_or_404(manageable_products(request.user), pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully.')
            return redirect('suppliers:product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'suppliers/product_form.html', {'form': form})

@login_required
def product_delete(request, pk):
    product = get_object_or_404(manageable_products(request.user, action='delete'), pk=pk)
    if request.method == 'POST':
        product_name = product.name
        product.is_active = False
        product.save(update_fields=['is_active'])
        messages.success(request, f'{product_name} was removed from the storefront.')
        return redirect('suppliers:product_list')
    return render(request, 'suppliers/product_confirm_delete.html', {'product': product})


@login_required
@require_POST
def update_supplier_profile(request):
    if not getattr(request.user, 'is_supplier', False):
        messages.error(request, 'Only suppliers can update supplier contact details.')
        return redirect('accounts:dashboard')
    supplier, _ = Supplier.objects.get_or_create(
        user=request.user,
        defaults={'company_name': request.user.username},
    )
    form = SupplierProfileForm(request.POST, instance=supplier)
    if form.is_valid():
        form.save()
        messages.success(request, 'Supplier profile and WhatsApp contact details updated.')
    else:
        messages.error(request, f'Please correct the supplier profile fields: {form.errors.as_text()}')
    return redirect('dashboard:supplier_dashboard')


def product_detail(request, pk):
    product = get_object_or_404(
        shopper_visible_products(),
        pk=pk,
    )
    if not record_customer_product_view(product, request.user):
        raise Http404("This listing has reached its weekly customer-view limit.")
    supplier = product.supplier
    
    return render(request, 'products/product_detail.html', {
        'product': product,
        'supplier': supplier,
        'supplier_whatsapp_url': (
            f"https://wa.me/{supplier.whatsapp_number}"
            f"?text={quote(f'Hi {supplier.company_name or supplier.user.username}, I am interested in {product.name}.')}"
            if supplier.whatsapp_number else ''
        ),
    })


@login_required
@require_POST
def start_premium_subscription(request):
    if not getattr(request.user, 'is_supplier', False):
        messages.error(request, 'Only suppliers can purchase a supplier subscription.')
        return redirect('accounts:dashboard')

    supplier = get_object_or_404(Supplier, user=request.user)
    phone_number = request.POST.get('phone_number', '').strip()
    if not phone_number:
        messages.error(request, 'Enter the M-Pesa phone number to charge.')
        return redirect('dashboard:supplier_dashboard')

    payment = SupplierSubscriptionPayment.objects.create(
        supplier=supplier,
        phone_number=phone_number,
    )
    from apps.orders.mpesa_utils import mpesa_service
    from django.urls import reverse
    callback_url = settings.MPESA_SUPPLIER_CALLBACK_URL
    if not callback_url:
        callback_base = urlsplit(settings.MPESA_CONFIG['CALLBACK_URL'])
        callback_url = urlunsplit((
            callback_base.scheme,
            callback_base.netloc,
            reverse('suppliers:subscription_callback'),
            '',
            '',
        ))
    result = mpesa_service.initiate_stk_push(
        phone_number=phone_number,
        amount=payment.amount,
        order_number=f"SUPPLIER-{payment.pk}",
        account_reference=f"VM-SUB-{payment.pk}",
        callback_url=callback_url,
    )
    if not result.get('success') or not result.get('checkout_request_id'):
        payment.status = 'failed'
        payment.save(update_fields=['status'])
        messages.error(request, f"Could not initiate M-Pesa payment: {result.get('error', 'Missing checkout request ID')}")
        return redirect('dashboard:supplier_dashboard')

    payment.checkout_request_id = result['checkout_request_id']
    payment.save(update_fields=['checkout_request_id'])
    messages.success(request, 'M-Pesa prompt sent. Premium activates for 7 days after payment is confirmed.')
    return redirect('dashboard:supplier_dashboard')


@csrf_exempt
@require_POST
def supplier_subscription_callback(request):
    try:
        callback_data = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'message': 'Invalid callback payload.'}, status=400)

    stk_callback = callback_data.get('Body', {}).get('stkCallback', {})
    checkout_request_id = stk_callback.get('CheckoutRequestID')
    if not checkout_request_id:
        return JsonResponse({'success': False, 'message': 'Missing checkout request ID.'}, status=400)

    try:
        with transaction.atomic():
            payment = SupplierSubscriptionPayment.objects.select_for_update().select_related('supplier').get(
                checkout_request_id=checkout_request_id,
            )
            if payment.status == 'completed':
                return JsonResponse({'success': True, 'message': 'Subscription payment was already processed.'})

            try:
                result_code = int(stk_callback.get('ResultCode'))
            except (TypeError, ValueError):
                result_code = None
            if result_code != 0:
                payment.status = 'failed'
                payment.save(update_fields=['status'])
                return JsonResponse({'success': True, 'message': 'Subscription payment was not completed.'})

            items = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            metadata = {item.get('Name'): item.get('Value') for item in items}
            try:
                paid_amount = Decimal(str(metadata.get('Amount')))
            except (InvalidOperation, TypeError, ValueError):
                payment.status = 'failed'
                payment.save(update_fields=['status'])
                return JsonResponse({'success': False, 'message': 'Callback did not include a valid payment amount.'}, status=400)

            if paid_amount != payment.amount or not metadata.get('MpesaReceiptNumber'):
                payment.status = 'failed'
                payment.save(update_fields=['status'])
                return JsonResponse({'success': False, 'message': 'A valid payment amount and M-Pesa receipt are required.'}, status=400)

            payment.status = 'completed'
            payment.receipt_number = str(metadata.get('MpesaReceiptNumber', ''))
            payment.confirmed_at = timezone.now()
            payment.save(update_fields=['status', 'receipt_number', 'confirmed_at'])
            payment.supplier.subscription_expires_at = payment.confirmed_at + timedelta(days=7)
            payment.supplier.save(update_fields=['subscription_expires_at'])
    except SupplierSubscriptionPayment.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Subscription payment not found.'}, status=404)

    return JsonResponse({'success': True, 'message': 'Subscription payment confirmed.'})


@login_required
@transaction.atomic
def create_order_for_supplier(request):
    """Allow a supplier to create an order for any product."""
    # ensure supplier profile
    supplier = Supplier.objects.filter(user=request.user).first()
    if not supplier:
        messages.error(request, 'You must have a supplier profile to create orders.')
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        form = SupplierOrderForm(request.POST, request.FILES, supplier=supplier)
        if form.is_valid():
            # Get cleaned data
            product_name = form.cleaned_data['product_name']
            quantity = form.cleaned_data['quantity']
            price = form.cleaned_data['price']
            available_quantity = form.cleaned_data['available_quantity']
            supplier_name = form.cleaned_data['supplier_name']
            supplier_phone = form.cleaned_data['supplier_phone']
            supplier_location = form.cleaned_data['supplier_location']
            product_image = form.cleaned_data.get('product_image')
            offer = form.cleaned_data.get('offer', '')  # Get the offer field

            # Update supplier information if changed
            supplier.company_name = supplier_name
            supplier.contact_number = supplier_phone
            supplier.location = supplier_location
            supplier.save()

            supplier = Supplier.objects.select_for_update().get(pk=supplier.pk)
            if not Product.objects.filter(name__iexact=product_name, supplier=supplier).exists():
                post_limit = product_post_limit(supplier)
                if product_posts_in_last_week(supplier) >= post_limit:
                    messages.error(
                        request,
                        f'Your current plan allows {post_limit} new product posts per rolling 7-day period.',
                    )
                    return redirect('dashboard:supplier_dashboard')

            # Get or create the product
            product, created = Product.objects.get_or_create(
                name__iexact=product_name,
                supplier=supplier,
                defaults={
                    'name': product_name.title(),
                    'description': f'{product_name.title()} product',
                    'category': product_name.lower(),
                    'cost': price,  # Use the price from the form
                    'available_quantity': available_quantity,  # Set stock quantity
                    'location': supplier.location or 'N/A',  # Add required location field
                    'offer': offer,  # Save the offer to the product
                }
            )

            # If product already exists, update the stock quantity and offer
            if not created:
                product.available_quantity = available_quantity
                product.offer = offer  # Update the offer
                product.save()

            # Handle product image upload if provided
            if product_image:
                # Save the image to media directory
                import os
                from django.conf import settings
                from django.core.files.storage import default_storage
                from django.core.files.base import ContentFile

                # Create a unique filename
                ext = os.path.splitext(product_image.name)[1]
                filename = f"product_{product.id}_{product_name.replace(' ', '_')}{ext}"

                # Save the file
                file_path = os.path.join('product_images', filename)
                path = default_storage.save(file_path, ContentFile(product_image.read()))

                # Update product with image URL (relative path)
                product.image_url = path
                product.save()

            # Create order
            order = Order.objects.create(
                product=product,
                quantity=quantity,
                price=price,  # Set the price from the form
                ordering_supplier=request.user,  # Track which supplier created this order
                offer=offer,  # Save the offer to the order
            )

            messages.success(request, f'Order created (#{order.order_number}). Product "{product.name}" {"created" if created else "updated"}.')
            # Redirect to supplier dashboard since this is a supplier creating the order
            return redirect('dashboard:supplier_dashboard')
        else:
            messages.error(request, f'Form validation failed: {form.errors}')
    else:
        form = SupplierOrderForm(supplier=supplier)

    return render(request, 'suppliers/supplier_create_order.html', {
        'form': form,
        'supplier': supplier,
    })


@login_required
def sell_all_orders(request):
    """Mark all pending orders for this supplier as completed (sold)."""
    supplier = Supplier.objects.filter(user=request.user).first()
    if not supplier:
        messages.error(request, 'You must have a supplier profile to perform this action.')
        return redirect('accounts:dashboard')

    pending_qs = Order.objects.filter(supplier=supplier, status='pending')
    count = pending_qs.count()
    if count == 0:
        messages.info(request, 'No pending orders to sell.')
    else:
        pending_qs.update(status='completed')
        messages.success(request, f'Marked {count} order(s) as completed.')

    return redirect('accounts:dashboard')


@login_required
def order_detail(request, pk):
    """View order details for suppliers."""
    order = get_object_or_404(Order, Q(pk=pk) & (Q(product__supplier__user=request.user) | Q(ordering_supplier=request.user)))

    # Handle GET actions for status updates (from dashboard links)
    if getattr(request.user, 'is_supplier', False):
        action = request.GET.get('action')
        # Handle mark_shipped (In Transit) - works from paid, pending, or any non-completed status
        if action == 'mark_shipped' and order.status in ['pending', 'paid', 'saved', 'complete_waiting_transport']:
            order.status = 'shipped'
            order.save()
            messages.success(request, 'Order marked as in transit (shipped).')
            return redirect('dashboard:supplier_dashboard')
        # Handle mark_complete - works from any status except already completed
        elif action == 'mark_complete' and order.status != 'completed':
            order.status = 'completed'
            order.save()
            # Send completion email to customer
            try:
                from apps.orders.views import send_order_completion_email_to_customer
                send_order_completion_email_to_customer(order)
            except Exception as e:
                print(f"Failed to send order completion email: {str(e)}")
            messages.success(request, 'Order marked as completed.')
            return redirect('dashboard:supplier_dashboard')

    return render(request, 'orders/order_detail.html', {'order': order})
