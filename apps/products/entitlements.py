from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import Product, ProductView

FREE_WEEKLY_PRODUCT_VIEW_LIMIT = 50
FREE_WEEKLY_PRODUCT_POST_LIMIT = 100
PREMIUM_WEEKLY_PRODUCT_POST_LIMIT = 300


def current_week_start():
    today = timezone.localdate()
    return today - timedelta(days=today.weekday())


def shopper_visible_products():
    week_start = current_week_start()
    capped_products = (
        ProductView.objects.filter(week_start=week_start)
        .values('product_id')
        .annotate(customer_count=Count('customer_id', distinct=True))
        .filter(customer_count__gte=FREE_WEEKLY_PRODUCT_VIEW_LIMIT)
        .values('product_id')
    )
    return (
        Product.objects.filter(
            category__in=dict(Product.CATEGORY_CHOICES),
            is_active=True,
        )
        .filter(
            Q(supplier__subscription_expires_at__gt=timezone.now())
            | ~Q(pk__in=capped_products)
        )
    )


def record_customer_product_view(product, user):
    if not getattr(user, 'is_authenticated', False) or getattr(user, 'user_type', None) != 'customer':
        return True
    if product.supplier.is_premium:
        return True

    week_start = current_week_start()
    with transaction.atomic():
        Product.objects.select_for_update().get(pk=product.pk)
        existing = ProductView.objects.filter(
            product=product,
            customer=user,
            week_start=week_start,
        ).exists()
        if existing:
            return True

        customer_count = ProductView.objects.filter(
            product=product,
            week_start=week_start,
        ).values('customer_id').distinct().count()
        if customer_count >= FREE_WEEKLY_PRODUCT_VIEW_LIMIT:
            return False

        ProductView.objects.create(
            product=product,
            customer=user,
            week_start=week_start,
        )
    return True


def product_post_limit(supplier):
    return (
        PREMIUM_WEEKLY_PRODUCT_POST_LIMIT
        if supplier.is_premium
        else FREE_WEEKLY_PRODUCT_POST_LIMIT
    )


def product_posts_in_last_week(supplier):
    since = timezone.now() - timedelta(days=7)
    return Product.objects.filter(
        supplier=supplier,
        created_at__gte=since,
    ).count()
