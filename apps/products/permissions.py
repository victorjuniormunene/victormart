from apps.products.models import Product
from apps.suppliers.models import Supplier


def manageable_products(user, action='change'):
    if user.is_superuser or (
        user.is_staff and user.has_perm(f'products.{action}_product')
    ):
        return Product.objects.all()

    supplier = Supplier.objects.filter(user=user).first()
    if supplier and getattr(user, 'is_supplier', False):
        return Product.objects.filter(supplier=supplier)

    return Product.objects.none()
