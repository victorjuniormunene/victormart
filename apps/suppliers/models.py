from django.db import models
from django.conf import settings
from django.utils import timezone


class Supplier(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    contact_number = models.CharField(max_length=15, blank=True)
    subscription_expires_at = models.DateTimeField(blank=True, null=True)

    @property
    def is_premium(self):
        return bool(self.subscription_expires_at and self.subscription_expires_at > timezone.now())

    @property
    def whatsapp_number(self):
        digits = ''.join(character for character in self.contact_number if character.isdigit())
        if digits.startswith('0'):
            return f'254{digits[1:]}'
        if digits.startswith('254'):
            return digits
        return f'254{digits}' if digits else ''

    def __str__(self):
        return self.company_name or getattr(self.user, 'username', 'supplier')


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

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='supplier_products')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    image_url = models.URLField(blank=True, null=True)
    available_quantity = models.PositiveIntegerField(default=0)
    
    # Offer field for supplier offers
    offer = models.CharField(max_length=50, blank=True, null=True, choices=[
        ('', 'No Offer'),
        ('free_delivery', 'Free Delivery'),
        ('10_percent_discount', '10% Discount'),
    ], help_text="Special offer applied to this product")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SupplierSubscriptionPayment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='subscription_payments',
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=500)
    phone_number = models.CharField(max_length=15)
    checkout_request_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    receipt_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.supplier} premium subscription ({self.status})"
