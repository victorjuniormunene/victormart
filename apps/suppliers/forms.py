from django import forms
from apps.products.forms import ProductForm
from apps.orders.models import Order
from .models import Supplier


class SupplierProfileForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ('company_name', 'location', 'contact_number')
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_number': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'tel',
                'placeholder': '07XXXXXXXX',
            }),
        }


class SupplierOrderForm(forms.Form):
    # Product name selection from predefined list

    PRODUCT_CHOICES = [
        ('', 'Select Product'),
        ('smartphone', 'Smartphone / Tablet'),
        ('laptop', 'Laptop / Computer'),
        ('mens_fashion', "Men's Clothing"),
        ('women_fashion', "Women's Clothing"),
        ('shoes', 'Shoes & Fashion Accessories'),
        ('electronics', 'Electronics & Gadgets'),
        ('home', 'Home & Furniture'),
        ('appliances', 'Home Appliances'),
        ('kitchen', 'Kitchen Products'),
        ('beauty', 'Beauty & Personal Care'),
        ('sports', 'Sports & Outdoors'),
        ('baby', 'Baby Products'),
    ]

    # Offer choices
    OFFER_CHOICES = [
        ('', 'No Offer'),
        ('free_delivery', 'Free Delivery'),
        ('10_percent_discount', '10% Discount'),
    ]
    
    offer = forms.ChoiceField(
        choices=OFFER_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )

    product_name = forms.ChoiceField(
        choices=PRODUCT_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )

    # Product image upload
    product_image = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*'
        })
    )

    # Order details
    quantity = forms.IntegerField(
        min_value=1,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter quantity'
        })
    )

    # Product price
    price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter price per unit',
            'step': '0.01'
        })
    )

    # Stock quantity
    available_quantity = forms.IntegerField(
        min_value=0,
        required=True,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter stock quantity'
        })
    )

    # Supplier information (editable)
    supplier_name = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter supplier name'
        })
    )
    supplier_phone = forms.CharField(
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter supplier phone number'
        })
    )
    supplier_location = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter supplier location'
        })
    )



    def __init__(self, *args, **kwargs):
        supplier = kwargs.pop('supplier', None)
        super().__init__(*args, **kwargs)

        if supplier:
            # Pre-fill supplier information
            self.fields['supplier_name'].initial = supplier.company_name or supplier.user.username
            self.fields['supplier_phone'].initial = supplier.contact_number or 'N/A'
            self.fields['supplier_location'].initial = supplier.location or 'N/A'

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')

        if product and quantity:
            if quantity > product.available_quantity:
                raise forms.ValidationError(
                    f"Only {product.available_quantity} units available in stock."
                )

        return cleaned_data
