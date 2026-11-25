from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.db import transaction
from urllib.parse import quote
from django.views.decorators.http import require_POST
from datetime import datetime
from .models import Product
from .entitlements import (
    product_post_limit,
    product_posts_in_last_week,
    record_customer_product_view,
    shopper_visible_products,
)
from .forms import ProductForm
from .permissions import manageable_products
from .models import ProductReview
from .review_forms import ProductReviewForm
from apps.orders.models import Order, Cart
from apps.orders.forms import OrderForm
from apps.orders.mpesa_utils import initiate_mpesa_payment, mpesa_service
from apps.suppliers.models import Supplier

def retail_products():
    return shopper_visible_products()

def product_list(request):
    products = retail_products()

    # Handle sorting
    sort_by = request.GET.get('sort', 'name')  # Default to name
    if sort_by == 'name':
        products = products.order_by('name')
    elif sort_by == 'price-low':
        products = products.order_by('cost')
    elif sort_by == 'price-high':
        products = products.order_by('-cost')
    elif sort_by == 'newest':
        products = products.order_by('-id')  # Assuming higher id = newer

    # Handle search
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(supplier__company_name__icontains=search_query)
        )

    # Handle category filter
    category = request.GET.get('category', '')
    if category:
        products = products.filter(category=category)

    # Handle add to cart - only for authenticated customers
    if request.method == 'POST' and 'add_to_cart' in request.POST:
        if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
            messages.error(request, 'Only logged-in customers can add items to cart.')
            return redirect('accounts:login')

        product_id = request.POST.get('product_id')
        if product_id:
            try:
                product = retail_products().get(id=product_id)
                quantity = int(request.POST.get('quantity', 1))

                cart_item, created = Cart.objects.get_or_create(
                    user=request.user,
                    product=product,
                    defaults={'quantity': quantity}
                )
                if not created:
                    cart_item.quantity += quantity
                    cart_item.save()

                messages.success(request, f'Added {quantity} x {product.name} to your cart.')
                return redirect('products:cart')
            except Product.DoesNotExist:
                messages.error(request, 'Product not found.')
        else:
            messages.error(request, 'Product not selected.')

    # Handle order creation - only for authenticated customers
    if request.method == 'POST' and 'create_order' in request.POST:
        if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
            messages.error(request, 'Only logged-in customers can place orders.')
            return redirect('products:product_list')

        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            product_id = request.POST.get('product_id')
            if product_id:
                try:
                    product = retail_products().get(id=product_id)
                    order.product = product
                    order.customer = request.user
                    order.status = 'pending_payment'  # Set status to pending payment
                    order.save()

                    # Initiate M-Pesa payment if phone number provided
                    customer_number = request.POST.get('customer_number')
                    if customer_number:
                        from apps.orders.mpesa_utils import initiate_mpesa_payment
                        payment_result = initiate_mpesa_payment(order, customer_number)
                        if payment_result.get('success'):
                            messages.success(request, f'Order #{order.order_number} created and payment initiated successfully! Total: KSH {order.total_cost}')
                            return redirect('orders:payment', order_id=order.id)
                        else:
                            messages.warning(request, f'Order #{order.order_number} created successfully, but payment initiation failed. Please contact support.')
                            return redirect('orders:payment', order_id=order.id)
                    else:
                        messages.success(request, f'Order #{order.order_number} created successfully! Total: KSH {order.total_cost}')
                        return redirect('orders:payment', order_id=order.id)

                    # Redirect to payment page
                    return redirect('orders:payment', order_id=order.id)
                except Product.DoesNotExist:
                    messages.error(request, 'Product not found.')
            else:
                messages.error(request, 'Product not selected.')
        else:
            messages.error(request, 'Please fill in all required fields.')
    else:
        form = OrderForm()

    context = {
        'products': products,
        'form': form,
        'current_sort': sort_by,
        'search_query': search_query,
        'current_category': category,
        'selected_category': category,
        'retail_categories': Product.CATEGORY_CHOICES,
    }
    return render(request, 'products/product_list.html', context)

def product_detail(request, product_id):
    product = get_object_or_404(retail_products(), id=product_id)
    if not record_customer_product_view(product, request.user):
        from django.http import Http404
        raise Http404("This listing has reached its weekly customer-view limit.")

    # Handle add to cart - only for authenticated customers
    if request.method == 'POST' and 'add_to_cart' in request.POST:
        if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
            messages.error(request, 'Only logged-in customers can add items to cart.')
            return redirect('accounts:login')

        try:
            quantity = int(request.POST.get('quantity', 1))
        except (TypeError, ValueError):
            messages.error(request, 'Enter a valid quantity.')
            return redirect('products:product_detail', product_id=product.id)

        if quantity < 1:
            messages.error(request, 'Quantity must be at least one.')
            return redirect('products:product_detail', product_id=product.id)

        cart_item = Cart.objects.filter(user=request.user, product=product).first()
        current_quantity = cart_item.quantity if cart_item else 0
        if product.available_quantity < current_quantity + quantity:
            messages.error(request, f'Only {product.available_quantity} units are currently in stock.')
            return redirect('products:product_detail', product_id=product.id)

        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={'quantity': quantity}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        messages.success(request, f'Added {quantity} x {product.name} to your cart.')
        return redirect('products:product_detail', product_id=product.id)

    # Handle order creation - only for authenticated customers
    if request.method == 'POST' and 'create_order' in request.POST:
        if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
            messages.error(request, 'Only logged-in customers can place orders.')
            return redirect('products:product_detail', product_id=product_id)

        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.product = product
            order.customer = request.user
            order.status = 'pending_payment'  # Set status to pending payment
            order.save()

            # Initiate M-Pesa payment if phone number provided
            customer_number = request.POST.get('customer_number')
            if customer_number:
                from apps.orders.mpesa_utils import initiate_mpesa_payment
                payment_result = initiate_mpesa_payment(order, customer_number)
                if payment_result.get('success'):
                    messages.success(request, f'Order #{order.order_number} created and payment initiated successfully! Total: KSH {order.total_cost}')
                    return redirect('orders:payment', order_id=order.id)
                else:
                    messages.warning(request, f'Order #{order.order_number} created successfully, but payment initiation failed. Please contact support.')
                    return redirect('orders:payment', order_id=order.id)
            else:
                messages.success(request, f'Order #{order.order_number} created successfully! Total: KSH {order.total_cost}')
                return redirect('orders:payment', order_id=order.id)
        else:
            messages.error(request, 'Please fill in all required fields.')
            return redirect('products:product_detail', product_id=product_id)

    reviews = product.reviews.select_related('customer')
    review_summary = reviews.aggregate(average_rating=Avg('rating'), review_count=Count('id'))
    eligible_orders = Order.objects.none()
    existing_review_orders = set()
    if request.user.is_authenticated and request.user.user_type == 'customer':
        eligible_orders = Order.objects.filter(
            product=product,
            customer=request.user,
            status__in=['paid', 'shipped', 'complete_waiting_transport', 'completed'],
        ).order_by('-created_at')
        existing_review_orders = set(
            ProductReview.objects.filter(
                order__in=eligible_orders,
                customer=request.user,
            ).values_list('order_id', flat=True)
        )
    return render(request, 'products/product_detail.html', {
        'product': product,
        'reviews': reviews,
        'average_rating': review_summary['average_rating'],
        'review_count': review_summary['review_count'],
        'eligible_orders': eligible_orders,
        'existing_review_orders': existing_review_orders,
        'supplier_whatsapp_url': (
            f"https://wa.me/{product.supplier.whatsapp_number}"
            f"?text={quote(f'Hi {product.supplier.company_name or product.supplier.user.username}, I am interested in {product.name}.')}"
            if product.supplier.whatsapp_number else ''
        ),
        'review_form': ProductReviewForm(),
    })


@require_POST
def submit_product_review(request, product_id):
    if not request.user.is_authenticated or request.user.user_type != 'customer':
        messages.error(request, 'Log in as a customer to review a purchase.')
        return redirect('accounts:login')

    product = get_object_or_404(retail_products(), pk=product_id)
    order_id = request.POST.get('order_id')
    order = get_object_or_404(
        Order,
        pk=order_id,
        product=product,
        customer=request.user,
        status__in=['paid', 'shipped', 'complete_waiting_transport', 'completed'],
    )
    if ProductReview.objects.filter(order=order).exists():
        messages.error(request, 'You have already reviewed this purchase.')
        return redirect('products:product_detail', product_id=product.id)

    form = ProductReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.customer = request.user
        review.order = order
        review.save()
        messages.success(request, 'Thank you for reviewing your purchase.')
    else:
        messages.error(request, 'Please choose a rating and enter a valid review.')
    return redirect('products:product_detail', product_id=product.id)

@login_required
def product_create(request):
    if not getattr(request.user, 'is_supplier', False):
        messages.error(request, 'Only suppliers can create products.')
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            supplier, _ = Supplier.objects.get_or_create(
                user=request.user,
                defaults={'company_name': request.user.username},
            )
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
            return redirect('dashboard:supplier_dashboard')
    else:
        form = ProductForm()
    return render(request, 'suppliers/product_form.html', {'form': form})

@login_required
def product_update(request, product_id):
    product = get_object_or_404(manageable_products(request.user), id=product_id)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated successfully.')
            return redirect('products:product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'suppliers/product_form.html', {'form': form})

@login_required
def product_delete(request, product_id):
    product = get_object_or_404(manageable_products(request.user, action='delete'), id=product_id)
    if request.method == 'POST':
        product_name = product.name
        product.is_active = False
        product.save(update_fields=['is_active'])
        messages.success(request, f'{product_name} was removed from the storefront.')
        return redirect('products:product_list')
    return render(request, 'suppliers/product_confirm_delete.html', {'product': product})

@require_POST
def add_to_cart(request, product_id):
    if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
        messages.error(request, 'Only logged-in customers can add items to cart.')
        return redirect('accounts:login')

    product = get_object_or_404(retail_products(), id=product_id)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        messages.error(request, 'Enter a valid quantity.')
        return redirect('products:product_detail', product_id=product.id)
    if quantity < 1:
        messages.error(request, 'Quantity must be at least one.')
        return redirect('products:product_detail', product_id=product.id)

    cart_item = Cart.objects.filter(user=request.user, product=product).first()
    current_quantity = cart_item.quantity if cart_item else 0
    if product.available_quantity < current_quantity + quantity:
        messages.error(request, f'Only {product.available_quantity} units are currently in stock.')
        return redirect('products:product_detail', product_id=product.id)

    # Get or create cart item
    cart_item, created = Cart.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': quantity}
    )

    if not created:
        cart_item.quantity += quantity
        cart_item.save()

    messages.success(request, f'Added {quantity} x {product.name} to your cart.')
    return redirect('products:product_detail', product_id=product.id)

def cart(request):
    if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
        messages.error(request, 'Only logged-in customers can view their cart.')
        return redirect('accounts:login')

    cart_items = Cart.objects.filter(
        user=request.user,
        product__in=retail_products(),
    ).select_related('product__supplier')
    total_cost = sum(item.total_cost for item in cart_items)

    return render(request, 'products/cart.html', {
        'cart_items': cart_items,
        'total_cost': total_cost
    })

def remove_from_cart(request, cart_item_id):
    if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
        messages.error(request, 'Only logged-in customers can modify their cart.')
        return redirect('accounts:login')

    cart_item = get_object_or_404(Cart, id=cart_item_id, user=request.user)
    cart_item.delete()

    messages.success(request, f'Removed {cart_item.product.name} from your cart.')
    return redirect('products:cart')



def checkout(request):
    if not request.user.is_authenticated or getattr(request.user, 'user_type', None) != 'customer':
        messages.error(request, 'Only logged-in customers can checkout.')
        return redirect('accounts:login')

    if request.method == 'POST':
        cart_items = Cart.objects.filter(
            user=request.user,
            product__in=retail_products(),
        ).select_related('product__supplier')
        if not cart_items:
            messages.error(request, 'Your cart is empty.')
            return redirect('products:cart')

        unavailable_items = [
            f'{item.product.name} (available: {item.product.available_quantity})'
            for item in cart_items
            if item.quantity > item.product.available_quantity
        ]
        if unavailable_items:
            messages.error(request, 'Some cart quantities exceed current stock: ' + ', '.join(unavailable_items))
            return redirect('products:cart')

        customer_name = request.POST.get('customer_name')
        customer_number = request.POST.get('customer_number')
        customer_location = request.POST.get('customer_location')

        if not all([customer_name, customer_number, customer_location]):
            messages.error(request, 'Please fill in all required fields.')
            return redirect('products:checkout')

        # Create orders for each cart item
        created_orders = []
        total_amount = 0

        for cart_item in cart_items:
            # Automatically apply the product's offer if it has one
            product_offer = cart_item.product.offer if cart_item.product else None
            
            order = Order.objects.create(
                customer=request.user,
                product=cart_item.product,
                quantity=cart_item.quantity,
                price=cart_item.product.cost,
                customer_name=customer_name,
                customer_number=customer_number,
                customer_location=customer_location,
                status='pending_payment',  # Set status to pending payment
                offer=product_offer  # Automatically apply the product's offer
            )
            created_orders.append(order)
            total_amount += order.total_cost

        # Initiate bulk M-Pesa payment
        from apps.orders.mpesa_utils import initiate_bulk_mpesa_payment
        payment_result = initiate_bulk_mpesa_payment(created_orders, customer_number)

        if payment_result.get('success'):
            # Clear the cart after successful order creation and payment initiation
            cart_items.delete()
            messages.success(request, f'Orders created and payment initiated successfully! Total: KSH {total_amount}. Please check your phone and enter your M-Pesa PIN to complete the payment.')
            return redirect('accounts:dashboard')
        else:
            # Payment failed, but orders are created
            messages.warning(request, f'Orders created successfully, but payment initiation failed: {payment_result.get("error", "Unknown error")}. You can try payment again from your dashboard.')
            return redirect('accounts:dashboard')

    cart_items = Cart.objects.filter(
        user=request.user,
        product__category__in=dict(Product.CATEGORY_CHOICES),
        product__is_active=True,
    ).select_related('product__supplier')
    total_cost = sum(item.total_cost for item in cart_items)

    return render(request, 'products/checkout.html', {
        'cart_items': cart_items,
        'total_cost': total_cost
    })
