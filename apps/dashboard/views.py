from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse
from apps.suppliers.models import Supplier
from apps.products.models import Product
from apps.products.entitlements import product_post_limit, product_posts_in_last_week
from apps.orders.models import Order
from datetime import datetime

@login_required
def customer_dashboard_view(request):
    user = request.user

    # Ensure user has customer profile if needed (though not strictly required for dashboard)
    # Customer model exists but dashboard doesn't require it

    # Get orders for this user, excluding pending/saved orders
    orders = Order.objects.filter(
        customer=user
    ).exclude(
        status__in=['saved', 'pending_payment']
    ).order_by('-created_at')
    
    # Get pending payment orders for the Update Payment Status section
    pending_orders = Order.objects.filter(
        customer=user,
        status__in=['saved', 'pending_payment']
    ).order_by('-created_at')
    
    from apps.products.entitlements import shopper_visible_products
    products = shopper_visible_products()[:6]
    # Calculate stats
    total_orders = orders.count()
    completed_orders = orders.filter(status='completed').count()
    in_transit_orders = orders.filter(status='shipped').count()
    total_value = sum(order.total_cost or 0 for order in orders)

    context = {
        'orders': orders[:5],  # Show only recent 5 orders
        'pending_orders': pending_orders,  # Orders pending payment for manual update
        'products': products,
        'order_graph': None,  # Graph disabled for now
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'in_transit_orders': in_transit_orders,
        'total_value': total_value,
    }
    return render(request, 'dashboard/customer_dashboard.html', context)

@login_required
def order_history_view(request):
    orders = Order.objects.filter(customer=request.user)
    return render(request, 'dashboard/order_history.html', {'orders': orders})

@login_required(login_url='accounts:supplier_login')
def supplier_dashboard_view(request):
    """Dashboard for suppliers: show their products and orders."""
    from apps.suppliers.models import Supplier
    from apps.products.models import Product
    from apps.orders.models import Order

    user = request.user

    # Restrict access: only suppliers can view this page
    if not getattr(user, 'is_supplier', False):
        messages.error(request, 'You must be a supplier to access the supplier dashboard.')
        return redirect('accounts:supplier_login')

    # Get or create supplier profile
    supplier, created = Supplier.objects.get_or_create(
        user=user,
        defaults={
            'company_name': user.username,
            'location': '',
            'contact_number': ''
        }
    )

    if created:
        messages.info(request, 'Your supplier profile has been created. Please update your company details.')
    weekly_posts_used = product_posts_in_last_week(supplier)
    products = Product.objects.filter(
        supplier__user=user,
        category__in=dict(Product.CATEGORY_CHOICES),
    )

    # Show orders for this supplier (orders for products supplied by this supplier)
    # allow filtering by status via ?status=
    # Exclude orders created by this supplier themselves to differentiate from "Orders You Created"
    # Only show orders that have been paid or are in later stages
    status = request.GET.get('status')
    orders_qs = Order.objects.filter(
        product__supplier=supplier,
        status__in=['paid', 'shipped', 'complete_waiting_transport', 'completed']
    ).exclude(ordering_supplier=user)
    if status and status in dict(Order._meta.get_field('status').choices):
        orders_qs = orders_qs.filter(status=status)
    supplier_orders = orders_qs.order_by('-created_at')

    # Show orders created BY this supplier (supplier-created orders)
    # These are orders the supplier created for customers
    supplier_created_orders = Order.objects.filter(
        ordering_supplier=user
    ).distinct().order_by('-created_at')

    # counts per status for quick filtering UI
    from django.db import models as dj_models
    status_counts = orders_qs.values('status').order_by().annotate(count=dj_models.Count('id'))
    counts = {item['status']: item['count'] for item in status_counts}

    # All orders for this supplier's products (for the "All Orders for Your Products" section)
    # Exclude pending orders (saved and pending_payment)
    all_product_orders = Order.objects.filter(
        product__supplier=supplier
    ).exclude(
        status__in=['saved', 'pending_payment']
    ).order_by('-created_at')

    payment_orders = Order.objects.filter(
        product__supplier=supplier,
        customer__isnull=False,
    ).exclude(
        status='saved',
    ).select_related('product', 'customer').order_by('-created_at')
    completed_mpesa_orders = payment_orders.filter(payment_status='completed')
    mpesa_paid_revenue = sum(order.total_cost for order in completed_mpesa_orders)

    # Count completed orders for the dashboard stats
    completed_orders_count = supplier_orders.filter(status='completed').count()

    # Get unread messages count for the supplier
    from apps.messaging.models import Conversation
    unread_messages_count = 0
    try:
        supplier_conversations = Conversation.objects.filter(supplier=user)
        unread_messages_count = sum(conv.unread_count for conv in supplier_conversations)
    except:
        pass

    context = {
        'products': products,
        'supplier_orders': supplier_orders,
        'supplier_created_orders': supplier_created_orders,
        'all_product_orders': all_product_orders,
        'payment_orders': payment_orders,
        'mpesa_paid_order_count': completed_mpesa_orders.count(),
        'mpesa_paid_revenue': mpesa_paid_revenue,
        'order_status_counts': counts,
        'selected_status': status,
        'completed_orders_count': completed_orders_count,
        'unread_messages_count': unread_messages_count,
        'supplier': supplier,
        'is_premium_supplier': supplier.is_premium,
        'subscription_expires_at': supplier.subscription_expires_at,
        'weekly_posts_used': weekly_posts_used,
        'weekly_posts_limit': product_post_limit(supplier),
        'weekly_posts_remaining': max(0, product_post_limit(supplier) - weekly_posts_used),
        'subscription_payments': supplier.subscription_payments.all()[:10],
    }
    return render(request, 'dashboard/supplier_dashboard.html', context)

def generate_order_graph(user, dashboard_type):
    """Generate order graph data for dashboard visualization"""
    import matplotlib
    matplotlib.use('Agg')  # Use non-GUI backend
    import matplotlib.pyplot as plt
    import base64
    from io import BytesIO
    from django.db.models import Count

    # Get orders based on dashboard type
    if dashboard_type == 'customer':
        orders = Order.objects.filter(customer=user)
    else:
        # For supplier dashboard
        from apps.suppliers.models import Supplier
        try:
            supplier = Supplier.objects.get(user=user)
            orders = Order.objects.filter(product__supplier=supplier)
        except Supplier.DoesNotExist:
            return None

    # Get status distribution
    status_counts = orders.values('status').annotate(count=Count('id')).order_by('status')

    if not status_counts:
        return None

    labels = []
    sizes = []
    colors = []

    status_colors = {
        'saved': '#ffc107',
        'paid': '#17a2b8',
        'shipped': '#007bff',
        'complete_waiting_transport': '#fd7e14',
        'completed': '#28a745',
        'canceled': '#dc3545',
    }

    for item in status_counts:
        status = item['status']
        count = item['count']
        labels.append(status.replace('_', ' ').title())
        sizes.append(count)
        colors.append(status_colors.get(status, '#6c757d'))

    # Create pie chart
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    ax.set_title('Order Status Distribution')

    # Save to buffer
    buffer = BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight')
    buffer.seek(0)
    image_png = buffer.getvalue()
    buffer.close()

    # Encode to base64
    graphic = base64.b64encode(image_png).decode('utf-8')
    plt.close(fig)

    return graphic

@login_required
def download_customer_report(request):
    """Generate and download a customer activity report containing order details."""
    try:
        user = request.user

        # Allow all users to download customer reports for now
        # This ensures customers can always access their own data

        # Get user's orders - exclude saved and pending_payment like dashboard
        orders = Order.objects.filter(customer=user).exclude(status__in=['saved', 'pending_payment']).order_by('-created_at')

        # Generate PDF report
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO
        from datetime import datetime

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=1  # Center alignment
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=10,
            spaceBefore=10
        )

        # Header
        elements.append(Paragraph("VICTORMART", title_style))
        elements.append(Paragraph("Customer Activity Report", styles['Heading2']))
        elements.append(Spacer(1, 0.3*inch))

        # Customer Information
        elements.append(Paragraph("CUSTOMER INFORMATION", heading_style))
        customer_info = [
            ['Name:', user.get_full_name() or user.username],
            ['Email:', user.email or 'N/A'],
            ['Report Generated:', datetime.now().strftime('%d/%m/%Y %H:%M')],
            ['Report Date:', datetime.now().strftime('%B %d, %Y')],
        ]
        customer_table = Table(customer_info, colWidths=[2*inch, 4*inch])
        customer_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(customer_table)
        elements.append(Spacer(1, 0.2*inch))

        # Activity Summary
        elements.append(Paragraph("ACTIVITY SUMMARY", heading_style))
        total_orders = orders.count()
        completed_orders = orders.filter(status='completed').count()
        total_value = sum(order.total_cost or 0 for order in orders)

        summary_data = [
            ['Total Orders:', str(total_orders)],
            ['Completed Orders:', str(completed_orders)],
            ['Total Order Value:', f"KSH {total_value:,.2f}"],
        ]
        summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.2*inch))

        # Order Details
        if orders:
            elements.append(Paragraph("ORDER DETAILS", heading_style))
            order_data = [['Order #', 'Product', 'Quantity', 'Status', 'Date', 'Total (KSH)']]

            for order in orders:
                product_name = order.product.name if order.product else f"Plan: {order.plan_type or 'N/A'}"
                display_name = product_name[:30] + '...' if len(product_name) > 30 else product_name
                order_data.append([
                    order.order_number,
                    display_name,
                    str(order.quantity),
                    order.get_status_display(),
                    order.created_at.strftime('%d/%m/%Y'),
                    f"{order.total_cost or 0:,.2f}"
                ])

            order_table = Table(order_data, colWidths=[1*inch, 2.5*inch, 0.8*inch, 1.2*inch, 1*inch, 1*inch])
            order_table.setStyle(TableStyle([
                ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
                ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(order_table)
            elements.append(Spacer(1, 0.2*inch))
        else:
            elements.append(Paragraph("No orders found for this customer.", styles['Normal']))
            elements.append(Spacer(1, 0.2*inch))

        # Key Points Section
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("KEY POINTS & REMINDERS", heading_style))
        key_points = [
            "• Keep this report for your records and tax purposes",
            "• Contact suppliers directly for order status updates",
            "• Rate your experience to help improve our services",
            "• All payments are processed securely through M-Pesa",
            "• Orders typically ship within 2-3 business days",
            f"• Report generated on: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}",
        ]

        for point in key_points:
            elements.append(Paragraph(point, styles['Normal']))
            elements.append(Spacer(1, 0.1*inch))

        # Footer
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Thank you for choosing VictorMart!", styles['Normal']))
        elements.append(Paragraph("For support, contact the VictorMart team.", styles['Normal']))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)

        # Return as file download
        response = FileResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="customer_activity_report_{user.username}_{datetime.now().strftime("%Y%m%d")}.pdf"'
        return response

    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('home')

@login_required
def download_supplier_report(request):
    """Generate and download a supplier report as PDF showing orders from customers"""
    try:
        user = request.user

        # Check if user is a supplier
        if user.user_type != 'supplier':
            messages.error(request, 'You must be a supplier to access this report.')
            return redirect('accounts:dashboard')

        from apps.suppliers.models import Supplier
        supplier = Supplier.objects.get(user=user)

        # Get orders for this supplier's products - only paid/processed orders, exclude supplier-created orders
        orders = Order.objects.filter(
            product__supplier=supplier,
            status__in=['paid', 'shipped', 'complete_waiting_transport', 'completed']
        ).exclude(ordering_supplier=user).order_by('-created_at')

        # Generate PDF report
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO
        from datetime import datetime

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=1  # Center alignment
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=10,
            spaceBefore=10
        )

        # Header
        elements.append(Paragraph("CONSTRUCTION HUB", title_style))
        elements.append(Paragraph("Supplier Order Report", styles['Heading2']))
        elements.append(Spacer(1, 0.3*inch))

        # Supplier Information
        elements.append(Paragraph("SUPPLIER INFORMATION", heading_style))
        supplier_info = [
            ['Company Name:', supplier.company_name],
            ['Contact Person:', user.get_full_name() or user.username],
            ['Email:', user.email or 'N/A'],
            ['Phone:', supplier.contact_number or 'N/A'],
            ['Report Generated:', datetime.now().strftime('%d/%m/%Y %H:%M')],
            ['Report Date:', datetime.now().strftime('%B %d, %Y')],
        ]
        supplier_table = Table(supplier_info, colWidths=[2*inch, 4*inch])
        supplier_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(supplier_table)
        elements.append(Spacer(1, 0.2*inch))

        # Order Summary
        elements.append(Paragraph("ORDER SUMMARY", heading_style))
        total_orders = orders.count()
        completed_orders = orders.filter(status='completed').count()
        pending_orders = orders.filter(status='saved').count()
        paid_orders = orders.filter(status='paid').count()
        total_value = sum(order.total_cost for order in orders)

        summary_data = [
            ['Total Orders:', str(total_orders)],
            ['Completed Orders:', str(completed_orders)],
            ['Pending Orders:', str(pending_orders)],
            ['Paid Orders:', str(paid_orders)],
            ['Total Revenue:', f"KSH {total_value:,.2f}"],
        ]
        summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.2*inch))

        # Order Details
        if orders:
            elements.append(Paragraph("CUSTOMER ORDERS", heading_style))
            order_data = [['Order #', 'Customer', 'Product', 'Quantity', 'Status', 'Date', 'Total (KSH)']]

            for order in orders:
                customer_name = order.customer_name or (order.customer.get_full_name() if order.customer else 'N/A')
                order_data.append([
                    order.order_number,
                    customer_name[:20] + '...' if len(customer_name) > 20 else customer_name,
                    order.product.name[:25] + '...' if len(order.product.name) > 25 else order.product.name,
                    str(order.quantity),
                    order.get_status_display(),
                    order.created_at.strftime('%d/%m/%Y'),
                    f"{order.total_cost:,.2f}"
                ])

            order_table = Table(order_data, colWidths=[1*inch, 1.5*inch, 2*inch, 0.8*inch, 1.2*inch, 1*inch, 1.2*inch])
            order_table.setStyle(TableStyle([
                ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9),
                ('FONT', (0, 1), (-1, -1), 'Helvetica', 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(order_table)
        else:
            elements.append(Paragraph("No orders found for this supplier.", styles['Normal']))

        # Key Points Section
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("KEY POINTS & REMINDERS", heading_style))
        key_points = [
            "• Process orders promptly to maintain customer satisfaction",
            "• Contact customers directly for order clarifications",
            "• Update order status regularly in the system",
            "• All payments are processed through M-Pesa for security",
            "• Keep detailed records for accounting and tax purposes",
            "• Respond to customer inquiries within 24 hours",
            f"• Report generated on: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}",
        ]

        for point in key_points:
            elements.append(Paragraph(point, styles['Normal']))
            elements.append(Spacer(1, 0.1*inch))

        # Footer
        elements.append(Spacer(1, 0.2*inch))
        elements.append(Paragraph("Thank you for being a valued Construction Hub supplier!", styles['Normal']))
        elements.append(Paragraph("For support, contact us at suppliers@constructionhub.com", styles['Normal']))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)

        # Return as file download
        response = FileResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="supplier_orders_report_{supplier.company_name}_{datetime.now().strftime("%Y%m%d")}.pdf"'
        return response

    except Exception as e:
        messages.error(request, f'Error generating supplier report: {str(e)}')
        return redirect('accounts:dashboard')

@login_required
@login_required
def download_supplier_consolidated_report(request):
    """Generate and download a comprehensive consolidated supplier report as PDF showing all orders with full customer details"""
    try:
        user = request.user

        # Check if user is a supplier
        if user.user_type != 'supplier':
            messages.error(request, 'You must be a supplier to access this report.')
            return redirect('accounts:dashboard')

        from apps.suppliers.models import Supplier
        supplier = Supplier.objects.get(user=user)

        # Get all orders for this supplier's products
        orders = Order.objects.filter(product__supplier=supplier).order_by('-created_at')

        # Generate comprehensive PDF report
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from io import BytesIO
        from datetime import datetime

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=6,
            alignment=1  # Center alignment
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=10,
            spaceBefore=10
        )
        subheading_style = ParagraphStyle(
            'CustomSubHeading',
            parent=styles['Heading3'],
            fontSize=14,
            textColor=colors.HexColor('#2e7d32'),
            spaceAfter=8,
            spaceBefore=8
        )

        # Header
        elements.append(Paragraph("CONSTRUCTION HUB", title_style))
        elements.append(Paragraph("Comprehensive Supplier Order Report", styles['Heading2']))
        elements.append(Spacer(1, 0.3*inch))

        # Report Information
        elements.append(Paragraph("REPORT INFORMATION", heading_style))
        report_info = [
            ['Report Type:', 'Consolidated Supplier Order Report'],
            ['Generated For:', supplier.company_name or user.get_full_name()],
            ['Supplier ID:', f'SUP-{supplier.id:04d}'],
            ['Report Generated:', datetime.now().strftime('%d/%m/%Y %H:%M')],
            ['Report Date:', datetime.now().strftime('%B %d, %Y')],
            ['Time Period:', 'All Orders'],
            ['Total Orders:', str(orders.count())],
        ]
        report_table = Table(report_info, colWidths=[2.5*inch, 4*inch])
        report_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(report_table)
        elements.append(Spacer(1, 0.2*inch))

        # Supplier Information
        elements.append(Paragraph("SUPPLIER DETAILS", heading_style))
        supplier_info = [
            ['Company Name:', supplier.company_name],
            ['Contact Person:', user.get_full_name() or user.username],
            ['Email:', user.email or 'N/A'],
            ['Phone:', supplier.contact_number or 'N/A'],
            ['Location:', supplier.location or 'N/A'],
            ['Registration Date:', supplier.created_at.strftime('%d/%m/%Y') if hasattr(supplier, 'created_at') else 'N/A'],
        ]
        supplier_table = Table(supplier_info, colWidths=[2.5*inch, 4*inch])
        supplier_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(supplier_table)
        elements.append(Spacer(1, 0.2*inch))

        # Order Summary Statistics
        elements.append(Paragraph("ORDER SUMMARY STATISTICS", heading_style))
        total_orders = orders.count()
        completed_orders = orders.filter(status='completed').count()
        pending_orders = orders.filter(status='saved').count()
        paid_orders = orders.filter(status='paid').count()
        shipped_orders = orders.filter(status='shipped').count()
        canceled_orders = orders.filter(status='canceled').count()
        total_revenue = sum(order.total_cost for order in orders)
        total_quantity = sum(order.quantity for order in orders)

        summary_data = [
            ['Total Orders:', str(total_orders)],
            ['Completed Orders:', str(completed_orders)],
            ['Pending Orders:', str(pending_orders)],
            ['Paid Orders:', str(paid_orders)],
            ['Shipped Orders:', str(shipped_orders)],
            ['Canceled Orders:', str(canceled_orders)],
            ['Total Quantity Sold:', f"{total_quantity} units"],
            ['Total Revenue:', f"KSH {total_revenue:,.2f}"],
            ['Average Order Value:', f"KSH {total_revenue/total_orders:,.2f}" if total_orders > 0 else "KSH 0.00"],
        ]
        summary_table = Table(summary_data, colWidths=[2.5*inch, 4*inch])
        summary_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 0.2*inch))

        # Detailed Order Information
        if orders:
            elements.append(Paragraph("DETAILED ORDER INFORMATION", heading_style))
            elements.append(Paragraph("Complete list of all customer orders with full details", subheading_style))

            # Order Details Table
            order_data = [['Order #', 'Date', 'Customer Details', 'Product', 'Qty', 'Unit Price', 'Total', 'Status']]

            for order in orders:
                customer_details = f"{order.customer_name}\n{order.customer_number}\n{order.customer_location}"
                order_data.append([
                    order.order_number,
                    order.created_at.strftime('%d/%m/%Y\n%H:%M'),
                    customer_details,
                    order.product.name[:25] + '...' if len(order.product.name) > 25 else order.product.name,
                    str(order.quantity),
                    f"KSH {order.price:,.2f}",
                    f"KSH {order.total_cost:,.2f}",
                    order.get_status_display()
                ])

            order_table = Table(order_data, colWidths=[1*inch, 1.2*inch, 2*inch, 1.5*inch, 0.6*inch, 1*inch, 1*inch, 1*inch])
            order_table.setStyle(TableStyle([
                ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 9),
                ('FONT', (0, 1), (-1, -1), 'Helvetica', 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (2, 1), (2, -1), 'LEFT'),  # Customer details left-aligned
            ]))
            elements.append(order_table)
            elements.append(Spacer(1, 0.3*inch))

            # Customer Analysis Section
            elements.append(Paragraph("CUSTOMER ANALYSIS", heading_style))

            # Top Customers by Order Value
            customer_totals = {}
            for order in orders:
                customer_key = order.customer_name or "Unknown Customer"
                if customer_key not in customer_totals:
                    customer_totals[customer_key] = {'orders': 0, 'total': 0, 'quantity': 0}
                customer_totals[customer_key]['orders'] += 1
                customer_totals[customer_key]['total'] += order.total_cost
                customer_totals[customer_key]['quantity'] += order.quantity

            top_customers = sorted(customer_totals.items(), key=lambda x: x[1]['total'], reverse=True)[:10]

            if top_customers:
                elements.append(Paragraph("Top Customers by Order Value", subheading_style))
                customer_data = [['Customer Name', 'Orders', 'Total Quantity', 'Total Value']]
                for customer_name, data in top_customers:
                    customer_data.append([
                        customer_name[:30] + '...' if len(customer_name) > 30 else customer_name,
                        str(data['orders']),
                        str(data['quantity']),
                        f"KSH {data['total']:,.2f}"
                    ])

                customer_table = Table(customer_data, colWidths=[2.5*inch, 1*inch, 1.2*inch, 1.5*inch])
                customer_table.setStyle(TableStyle([
                    ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
                    ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(customer_table)
                elements.append(Spacer(1, 0.2*inch))

            # Product Performance
            product_totals = {}
            for order in orders:
                product_name = order.product.name
                if product_name not in product_totals:
                    product_totals[product_name] = {'orders': 0, 'quantity': 0, 'revenue': 0}
                product_totals[product_name]['orders'] += 1
                product_totals[product_name]['quantity'] += order.quantity
                product_totals[product_name]['revenue'] += order.total_cost

            top_products = sorted(product_totals.items(), key=lambda x: x[1]['revenue'], reverse=True)[:10]

            if top_products:
                elements.append(Paragraph("Product Performance Analysis", subheading_style))
                product_data = [['Product Name', 'Orders', 'Units Sold', 'Revenue']]
                for product_name, data in top_products:
                    product_data.append([
                        product_name[:35] + '...' if len(product_name) > 35 else product_name,
                        str(data['orders']),
                        str(data['quantity']),
                        f"KSH {data['revenue']:,.2f}"
                    ])

                product_table = Table(product_data, colWidths=[2.5*inch, 1*inch, 1.2*inch, 1.5*inch])
                product_table.setStyle(TableStyle([
                    ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
                    ('FONT', (0, 1), (-1, -1), 'Helvetica', 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ff7f31')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(product_table)
                elements.append(Spacer(1, 0.2*inch))

        else:
            elements.append(Paragraph("No orders found for this supplier.", styles['Normal']))

        # Key Performance Indicators
        elements.append(Paragraph("KEY PERFORMANCE INDICATORS", heading_style))
        kpi_data = [
            ['Conversion Rate:', f"{(paid_orders/total_orders*100):.1f}%" if total_orders > 0 else "0%"],
            ['Completion Rate:', f"{(completed_orders/total_orders*100):.1f}%" if total_orders > 0 else "0%"],
            ['Average Order Size:', f"{total_quantity/total_orders:.1f} units" if total_orders > 0 else "0 units"],
            ['Revenue per Order:', f"KSH {total_revenue/total_orders:,.2f}" if total_orders > 0 else "KSH 0.00"],
        ]
        kpi_table = Table(kpi_data, colWidths=[2.5*inch, 4*inch])
        kpi_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('FONT', (1, 0), (1, -1), 'Helvetica', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(kpi_table)
        elements.append(Spacer(1, 0.2*inch))

        # Recommendations Section
        elements.append(Paragraph("BUSINESS RECOMMENDATIONS", heading_style))
        recommendations = [
            "• Focus marketing efforts on your top-performing products",
            "• Follow up with customers who have pending orders",
            "• Consider loyalty programs for your best customers",
            "• Optimize inventory based on product performance data",
            "• Improve order fulfillment time to increase customer satisfaction",
            f"• This report covers all {total_orders} orders and KSH {total_revenue:,.2f} in revenue",
        ]

        for rec in recommendations:
            elements.append(Paragraph(rec, styles['Normal']))
            elements.append(Spacer(1, 0.1*inch))

        # Footer
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("Thank you for being a valued Construction Hub supplier!", styles['Normal']))
        elements.append(Paragraph("This comprehensive report provides complete visibility into your business performance.", styles['Normal']))
        elements.append(Paragraph(f"Report generated on: {datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}", styles['Normal']))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)

        # Return as file download
        response = FileResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="comprehensive_supplier_report_{supplier.company_name}_{datetime.now().strftime("%Y%m%d")}.pdf"'
        return response

    except Exception as e:
        messages.error(request, f'Error generating comprehensive supplier report: {str(e)}')
        return redirect('accounts:dashboard')
