from django.contrib import admin
from .models import Product

class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'supplier', 'category', 'cost', 'quality', 'available_quantity', 'is_active')
    list_filter = ('category', 'quality', 'supplier', 'is_active')
    search_fields = ('name', 'description', 'supplier__company_name')
    readonly_fields = ('id',)
    actions = ('archive_products',)

    @admin.action(description='Remove selected products from the storefront')
    def archive_products(self, request, queryset):
        archived_count = queryset.update(is_active=False)
        self.message_user(request, f'{archived_count} product(s) removed from the storefront.')

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(Product, ProductAdmin)