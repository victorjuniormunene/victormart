from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.suppliers.models import Supplier

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('phones', 'Phones & Tablets'),
        ('laptops', 'Computers & Laptops'),
        ('mens_fashion', "Men's Fashion"),
        ('women_fashion', "Women's Fashion"),
        ('shoes', 'Shoes & Accessories'),
        ('electronics', 'Electronics & Accessories'),
        ('home', 'Home & Furniture'),
        ('appliances', 'Home Appliances'),
        ('kitchen', 'Kitchen Products'),
        ('beauty', 'Beauty & Personal Care'),
        ('sports', 'Sports & Outdoors'),
        ('baby', 'Baby Products'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    image_url = models.URLField(blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    quality = models.CharField(max_length=50, choices=[
        ('standard', 'Standard'),
        ('premium', 'Premium'),
        ('high_end', 'High-End'),
    ], default='standard', help_text="Quality level of the product")
    location = models.CharField(max_length=255)
    available_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='products_from_products_app')
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Offer field for supplier offers
    offer = models.CharField(max_length=50, blank=True, null=True, choices=[
        ('', 'No Offer'),
        ('free_delivery', 'Free Delivery'),
        ('10_percent_discount', '10% Discount'),
    ], help_text="Special offer applied to this product")

    def __str__(self):
        return self.name

class ProductOrder(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    order_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order of {self.quantity} x {self.product.name} by {self.customer_name}"


class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='product_reviews')
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='product_review',
    )
    rating = models.PositiveSmallIntegerField(choices=[(value, value) for value in range(1, 6)])
    comment = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} review by {self.customer.username}"


class ProductView(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='customer_views')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_views',
    )
    week_start = models.DateField()
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'customer', 'week_start'],
                name='unique_customer_product_week_view',
            ),
        ]
