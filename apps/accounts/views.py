from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from .forms import UserRegistrationForm, UserLoginForm
from django.conf import settings
from apps.accounts.models import Customer, CustomUser
from apps.suppliers.models import Supplier
from django.db.models import Q


def register(request):
    """Handle user registration using UserRegistrationForm."""
    # Check for role parameter in query string
    initial_role = request.GET.get('role', 'customer')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # form.save already set password and saved user
            # Ensure profile objects exist depending on user_type
            if user.user_type == 'customer':
                Customer.objects.get_or_create(user=user)
            elif user.user_type == 'supplier':
                # Supplier signals may auto-create, but ensure one exists
                Supplier.objects.get_or_create(user=user, defaults={'company_name': user.username})

            # authenticate and login
            user = authenticate(username=user.username, password=form.cleaned_data['password1'])
            if user:
                login(request, user)
            return redirect('accounts:dashboard')
    else:
        form = UserRegistrationForm(initial={'role': initial_role})
    return render(request, 'accounts/register.html', {'form': form, 'initial_role': initial_role})


def unified_login(request):
    """Unified login view with single form that redirects based on user role"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Try to find user by username or email
        user = None
        if '@' in username:
            try:
                user = CustomUser.objects.get(email=username)
            except CustomUser.DoesNotExist:
                pass
        else:
            try:
                user = CustomUser.objects.get(username=username)
            except CustomUser.DoesNotExist:
                pass

        if user and user.check_password(password) and user.is_active:
            login(request, user)
            if user.is_staff or user.is_superuser:
                return redirect('admin:index')
            elif user.user_type == 'supplier':
                return redirect('dashboard:supplier_dashboard')
            else:
                return redirect('dashboard:customer_dashboard')
        else:
            messages.error(request, 'Invalid username or password.')

    form = UserLoginForm()
    
    # Get social account providers for Google/Facebook login buttons
    from allauth.socialaccount.models import SocialApp
    
    try:
        # Get social apps associated with current site
        # Use the provider's get_id() method which is the standard way
        social_apps = SocialApp.objects.filter(sites__id=settings.SITE_ID)
        providers = list(social_apps)
    except Exception as e:
        print(f"Error getting social providers: {e}")
        providers = []
    
    return render(request, 'accounts/login.html', {
        'form': form,
        'socialaccount_providers': providers
    })


def customer_login(request):
    """Customer-specific login view"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Try to find user by username or email
        user = None
        if '@' in username:
            try:
                user = CustomUser.objects.get(email=username)
            except CustomUser.DoesNotExist:
                pass
        else:
            try:
                user = CustomUser.objects.get(username=username)
            except CustomUser.DoesNotExist:
                pass

        if user and user.check_password(password) and user.is_active and user.user_type == 'customer':
            login(request, user)
            return redirect('dashboard:customer_dashboard')
        else:
            messages.error(request, 'Invalid username or password for customer login.')

    return render(request, 'accounts/customer_login.html')


def supplier_login(request):
    """Supplier-specific login view"""
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Try to find user by username or email
        user = None
        if '@' in username:
            try:
                user = CustomUser.objects.get(email=username)
            except CustomUser.DoesNotExist:
                pass
        else:
            try:
                user = CustomUser.objects.get(username=username)
            except CustomUser.DoesNotExist:
                pass

        if user and user.check_password(password) and user.is_active and user.user_type == 'supplier':
            login(request, user)
            return redirect('dashboard:supplier_dashboard')
        else:
            messages.error(request, 'Invalid username or password for supplier login.')

    return render(request, 'accounts/supplier_login.html')


@login_required
def dashboard(request):
    # Route staff admins, suppliers, and regular users to their respective dashboards.
    user = request.user
    if user.is_staff or user.is_superuser:
        return redirect('admin:index')
    if user.user_type == 'supplier':
        return redirect('dashboard:supplier_dashboard')
    return redirect('dashboard:customer_dashboard')


def contact(request):
    """Contact page with form to send messages to admin via email."""
    from django.core.mail import send_mail
    from django.contrib import messages
    from .models import ContactMessage

    if request.method == 'POST':
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        subject_text = request.POST.get('subject', '')
        message_text = request.POST.get('message', '')

        if name and email and message_text:
            # Save message to database
            contact_message = ContactMessage.objects.create(
                name=name,
                email=email,
                subject=subject_text,
                message=message_text
            )

            # Send email to admin
            admin_email = getattr(settings, 'ADMIN_EMAIL', 'victorjuniormunene@gmail.com')
            try:
                send_mail(
                    subject=f"New Contact Message from {name}: {subject_text}",
                    message=f"From: {name} ({email})\n\nMessage:\n{message_text}",
                    from_email=email,
                    recipient_list=[admin_email],
                    fail_silently=False,
                )
                messages.success(request, 'Your message has been sent to our admin team. Thank you!')
                return render(request, 'contact.html', {'submitted': True})
            except Exception as e:
                messages.error(request, f'Failed to send message: {str(e)}')
        else:
            messages.error(request, 'Please fill in all fields.')

    return render(request, 'contact.html')


def pricing(request):
    """Pricing page with product supplier plans and existing downloadable plans."""
    from apps.orders.models import Order
    from apps.accounts.models import ArchitecturalPlan

    # Fetch architectural plans from database
    db_plans = ArchitecturalPlan.objects.filter(is_active=True).order_by('plan_type')

    # If no plans in database, use fallback data
    if not db_plans.exists():
        # Fallback: Define default architectural plans
        base_plans = [
            {
                'plan_type': '2_bedroom',
                'name': '2 Bedroom Architectural Plan',
                'price': '20,000',
                'price_value': 20000,
                'period': '',
                'description': 'Complete architectural plan for a 2 bedroom house',
                'features': [
                    'Detailed floor plans',
                    'Elevation drawings',
                    'Section details',
                    'Material specifications',
                    'Construction guidelines',
                    'Digital format delivery',
                ],
            },
            {
                'plan_type': '3_bedroom',
                'name': '3 Bedroom Architectural Plan',
                'price': '25,000',
                'price_value': 25000,
                'period': '',
                'description': 'Comprehensive architectural plan for a 3 bedroom house',
                'features': [
                    'Detailed floor plans',
                    'Elevation drawings',
                    'Section details',
                    'Material specifications',
                    'Construction guidelines',
                    'Digital format delivery',
                    'Additional customization options',
                ],
                'featured': True
            },
        ]
    else:
        # Convert database plans to format compatible with template
        base_plans = []
        for plan in db_plans:
            plan_dict = {
                'plan_type': plan.plan_type,
                'name': plan.name,
                'price': f"{int(plan.price):,}",
                'price_value': int(plan.price),
                'period': '',
                'description': plan.description,
                'features': plan.features if plan.features else [],
            }
            # Mark 3 bedroom as featured
            if plan.plan_type == '3_bedroom':
                plan_dict['featured'] = True
            base_plans.append(plan_dict)

    # Check purchase status for architectural plans if user is authenticated
    pricing_plans = []
    if request.user.is_authenticated:
        for plan in base_plans:
            plan_copy = plan.copy()

            # Keep supplier memberships out of architectural plan purchases.
            if 'plan_type' not in plan:
                pricing_plans.append(plan_copy)
                continue

            # Check if user has purchased this plan
            plan_orders = Order.objects.filter(
                customer=request.user,
                plan_type=plan['plan_type']
            ).order_by('-created_at')

            if plan_orders.exists():
                latest_order = plan_orders.first()
                if latest_order.status == 'paid':
                    # User has paid - show download button
                    plan_copy['cta'] = 'Download Plan'
                    plan_copy['cta_link'] = f'/accounts/download_plan/{plan["plan_type"]}/'
                    plan_copy['status'] = 'paid'
                elif latest_order.status in ['pending_payment', 'saved']:
                    # Payment pending - show complete payment button
                    plan_copy['cta'] = 'Complete Payment'
                    plan_copy['cta_link'] = f'/accounts/complete_payment/{latest_order.id}/'
                    plan_copy['status'] = 'pending'
                else:
                    # Other status - show purchase again
                    plan_copy['cta'] = 'Purchase Now'
                    plan_copy['cta_link'] = f'/accounts/purchase_plan/{plan["plan_type"]}/'
            else:
                # No order exists - show purchase button
                plan_copy['cta'] = 'Purchase Now'
                plan_copy['cta_link'] = f'/accounts/purchase_plan/{plan["plan_type"]}/'

            pricing_plans.append(plan_copy)
    else:
        # For non-authenticated users, show purchase buttons
        for plan in base_plans:
            plan_copy = plan.copy()
            if 'plan_type' in plan:
                plan_copy['cta'] = 'Purchase Now'
                plan_copy['cta_link'] = f'/accounts/purchase_plan/{plan["plan_type"]}/'
            pricing_plans.append(plan_copy)

    return render(request, 'pricing.html', {'plans': pricing_plans})


def about(request):
    """About page with company information and testimonials."""
    testimonials = [
        {
            'name': 'John Smith',
            'company': 'BuildTech Contractors',
            'quote': 'Construction Hub transformed how we manage our projects. The platform is intuitive and has saved us countless hours on documentation.',
            'role': 'Project Manager'
        },
        {
            'name': 'Sarah Johnson',
            'company': 'Metropolitan Builders',
            'quote': 'Outstanding customer support and continuous improvements. This is exactly what the construction industry needed.',
            'role': 'Operations Director'
        },
        {
            'name': 'Mike Chen',
            'company': 'Premium Construction',
            'quote': 'The reporting features alone have improved our project visibility and stakeholder communication tremendously.',
            'role': 'Construction Manager'
        }
    ]
    
    return render(request, 'about.html', {'testimonials': testimonials})


def supplier_application(request):
    """Introduce supplier registration and route existing suppliers to their dashboard."""
    if request.user.is_authenticated:
        if request.user.is_supplier:
            return redirect('dashboard:supplier_dashboard')
        messages.info(request, 'Create a separate supplier account to list products.')
        return redirect('accounts:dashboard')
    return render(request, 'supplier_application.html')


@login_required
def purchase_plan(request, plan_type):
    """Create order for architectural plan and redirect to payment"""
    from apps.orders.models import Order
    from apps.products.models import Product
    from django.shortcuts import redirect
    from django.contrib import messages

    # Validate plan type
    plan_prices = {
        '2_bedroom': 20000,
        '3_bedroom': 25000
    }

    if plan_type not in plan_prices:
        messages.error(request, 'Invalid plan type.')
        return redirect('accounts:pricing')

    price = plan_prices[plan_type]

    # Check if user already has a paid order for this plan
    existing_paid_order = Order.objects.filter(
        customer=request.user,
        plan_type=plan_type,
        status='paid'
    ).exists()

    if existing_paid_order:
        messages.info(request, 'You have already purchased this plan.')
        return redirect('accounts:pricing')

    # Create a dummy product for the plan (or find existing one)
    # For now, we'll create orders without a product since these are digital plans
    order = Order.objects.create(
        customer=request.user,
        plan_type=plan_type,
        quantity=1,
        price=price,
        status='pending_payment',
        customer_name=request.user.get_full_name() or request.user.username,
        customer_number='',  # Will be filled during payment
        customer_location=''  # Will be filled during payment
    )

    # Redirect to payment page
    return redirect('orders:payment', order_id=order.id)


@login_required
def complete_payment(request, order_id):
    """Redirect to payment page for existing order"""
    from apps.orders.models import Order
    from django.shortcuts import redirect, get_object_or_404
    from django.contrib import messages

    order = get_object_or_404(Order, id=order_id, customer=request.user)

    # Check if already paid
    if order.status == 'paid':
        messages.info(request, 'This order has already been paid for.')
        return redirect('accounts:pricing')

    # Redirect to payment page
    return redirect('orders:payment', order_id=order.id)


@login_required
def download_plan(request, plan_type):
    """Download architectural plan image after payment verification"""
    from apps.orders.models import Order
    from django.http import FileResponse
    from django.contrib import messages
    import os
    from django.conf import settings

    # Check if user has paid for this plan type
    paid_orders = Order.objects.filter(
        customer=request.user,
        plan_type=plan_type,
        status='paid'
    )

    if not paid_orders.exists():
        messages.error(request, 'You have not purchased this plan or payment is not complete.')
        return redirect('accounts:pricing')

    # Map plan types to image files
    image_files = {
        '2_bedroom': '2 bedroom plan.jpg',
        '3_bedroom': '3 bedroom.jpg'
    }

    if plan_type not in image_files:
        messages.error(request, 'Invalid plan type.')
        return redirect('accounts:pricing')

    image_filename = image_files[plan_type]
    image_path = f'static/images/{image_filename}'

    try:
        # Return file as download
        file_path = os.path.join(settings.BASE_DIR, image_path)
        if os.path.exists(file_path):
            response = FileResponse(open(file_path, 'rb'), content_type='image/jpeg')
            response['Content-Disposition'] = f'attachment; filename="{image_filename}"'
            return response
        else:
            messages.error(request, 'Plan file not found. Please contact support.')
            return redirect('accounts:pricing')
    except Exception as e:
        messages.error(request, f'Error downloading file: {str(e)}')
        return redirect('accounts:pricing')


@login_required
def download_plan_receipt(request, plan_type):
    """Download plan purchase receipt PDF after payment verification"""
    from apps.orders.models import Order
    from django.http import HttpResponse
    from django.contrib import messages
    from .pdf_utils import generate_plan_receipt_pdf

    # Check if user has paid for this plan type
    paid_orders = Order.objects.filter(
        customer=request.user,
        plan_type=plan_type,
        status='paid'
    )

    if not paid_orders.exists():
        messages.error(request, 'You have not purchased this plan or payment is not complete.')
        return redirect('accounts:pricing')

    # Get the latest paid order
    order = paid_orders.first()

    # Map plan types to plan names and prices
    plan_details = {
        '2_bedroom': {'name': '2 Bedroom Architectural Plan', 'price': 20000},
        '3_bedroom': {'name': '3 Bedroom Architectural Plan', 'price': 25000}
    }

    if plan_type not in plan_details:
        messages.error(request, 'Invalid plan type.')
        return redirect('accounts:pricing')

    plan_name = plan_details[plan_type]['name']
    plan_price = plan_details[plan_type]['price']
    customer_name = request.user.get_full_name() or request.user.username
    customer_email = request.user.email

    try:
        # Generate PDF
        pdf_buffer = generate_plan_receipt_pdf(plan_name, plan_price, customer_name, customer_email)

        # Return PDF as download
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="plan_receipt_{plan_type}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f'Error generating receipt: {str(e)}')
        return redirect('accounts:pricing')


def home(request):
    """Render the storefront using currently available marketplace listings."""
    from django.db.models import Count
    from apps.products.entitlements import shopper_visible_products
    from apps.products.models import Product

    available_products = shopper_visible_products().filter(
        available_quantity__gt=0,
    )
    category_counts = {
        row['category']: row['product_count']
        for row in available_products.values('category').annotate(product_count=Count('pk'))
    }
    home_categories = [
        {
            'slug': category,
            'label': label,
            'count': category_counts.get(category, 0),
        }
        for category, label in Product.CATEGORY_CHOICES
    ]
    context = {
        'featured_products': available_products.select_related(
            'supplier',
            'supplier__user',
        ).order_by('-created_at', '-id')[:8],
        'home_categories': home_categories,
        'available_product_count': available_products.count(),
        'active_seller_count': available_products.values('supplier_id').distinct().count(),
    }
    return render(request, 'home.html', context)


@login_required
def send_email_to_user(request):
    """Admin view to send email to a user."""
    from django.core.mail import send_mail
    from django.http import JsonResponse
    from django.views.decorators.http import require_http_methods
    import json

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            recipient_email = data.get('email', '')
            subject = data.get('subject', '')
            message = data.get('message', '')

            if not recipient_email or not subject or not message:
                return JsonResponse({'success': False, 'error': 'All fields are required'}, status=400)

            # Get admin email for from_email
            admin_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'info@constructionhub.co.ke')

            # Send the email
            send_mail(
                subject=subject,
                message=message,
                from_email=admin_email,
                recipient_list=[recipient_email],
                fail_silently=False,
            )

            return JsonResponse({'success': True, 'message': f'Email sent to {recipient_email}'})

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)
