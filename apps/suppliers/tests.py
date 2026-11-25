from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Supplier, Product
from apps.products.models import Product as RetailProduct
from apps.products.models import ProductView
from apps.products.entitlements import current_week_start
from apps.orders.models import Order
from apps.messaging.models import Conversation
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch
import json

class SupplierModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.supplier = Supplier.objects.create(user=self.user, company_name="Test Supplier", location="Test Location")

    def test_supplier_creation(self):
        self.assertEqual(self.supplier.company_name, "Test Supplier")
        self.assertEqual(self.supplier.location, "Test Location")

class ProductModelTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.supplier = Supplier.objects.create(user=self.user, company_name="Test Supplier", location="Test Location")
        self.product = Product.objects.create(name="Test Product", cost=100.00, supplier=self.supplier)

    def test_product_creation(self):
        self.assertEqual(self.product.name, "Test Product")
        self.assertEqual(self.product.cost, 100.00)
        self.assertEqual(self.product.supplier, self.supplier)


class SupplierProductManagementTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.supplier_user = user_model.objects.create_user(
            username='catalog_supplier',
            password='test-password',
            user_type='supplier',
        )
        self.supplier = Supplier.objects.create(
            user=self.supplier_user,
            company_name='Catalog Supplier',
            location='Nairobi',
        )
        other_user = user_model.objects.create_user(
            username='other_supplier',
            password='test-password',
            user_type='supplier',
        )
        self.other_supplier = Supplier.objects.create(
            user=other_user,
            company_name='Other Supplier',
        )
        self.product = RetailProduct.objects.create(
            name='Supplier Phone',
            description='Phone details',
            category='phones',
            cost='10000.00',
            quality='standard',
            location='Nairobi',
            available_quantity=4,
            supplier=self.supplier,
        )
        self.other_product = RetailProduct.objects.create(
            name='Other Supplier Phone',
            description='Private listing',
            category='phones',
            cost='12000.00',
            location='Nairobi',
            supplier=self.other_supplier,
        )
        self.client.login(username='catalog_supplier', password='test-password')

    def product_form_data(self, **overrides):
        data = {
            'name': 'New VictorMart Product',
            'description': 'Full product specifications and condition.',
            'category': 'phones',
            'cost': '15000.00',
            'quality': 'premium',
            'location': 'Nairobi',
            'image_url': 'https://example.com/product.jpg',
            'available_quantity': '6',
            'offer': '',
            'is_active': 'on',
        }
        data.update(overrides)
        return data

    def test_supplier_can_create_product_with_full_details(self):
        from django.urls import reverse

        response = self.client.post(
            reverse('suppliers:product_create'),
            self.product_form_data(),
        )

        self.assertRedirects(response, reverse('suppliers:product_list'))
        product = RetailProduct.objects.get(name='New VictorMart Product')
        self.assertEqual(product.supplier, self.supplier)
        self.assertEqual(product.description, 'Full product specifications and condition.')
        self.assertEqual(product.quality, 'premium')
        self.assertEqual(product.available_quantity, 6)

    def test_supplier_listing_is_visible_with_required_details_to_shoppers(self):
        from django.urls import reverse

        self.product.description = '128GB storage, AMOLED display and fast charging.'
        self.product.image_url = 'https://example.com/phone.jpg'
        self.product.save()

        listing_response = self.client.get(reverse('suppliers:product_list'))
        detail_response = self.client.get(
            reverse('suppliers:product_detail', args=[self.product.pk]),
        )

        self.assertEqual(listing_response.status_code, 200)
        self.assertContains(listing_response, self.product.name)
        self.assertContains(listing_response, 'Catalog Supplier')
        self.assertContains(listing_response, 'Nairobi')
        self.assertContains(listing_response, 'Available stock')
        self.assertContains(listing_response, 'Standard')
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'KSH 10000.00')
        self.assertContains(detail_response, 'Catalog Supplier')
        self.assertContains(detail_response, 'Nairobi')
        self.assertContains(detail_response, 'Standard')
        self.assertContains(detail_response, '4')
        self.assertContains(detail_response, '128GB storage')

    def test_supplier_can_edit_and_delete_own_product(self):
        from django.urls import reverse

        response = self.client.post(
            reverse('suppliers:product_edit', args=[self.product.pk]),
            self.product_form_data(name='Updated Product', cost='17500.00'),
        )
        self.assertRedirects(response, reverse('suppliers:product_list'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Updated Product')
        self.assertEqual(str(self.product.cost), '17500.00')

        response = self.client.get(
            reverse('suppliers:product_delete', args=[self.product.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RetailProduct.objects.filter(pk=self.product.pk).exists())

        order = Order.objects.create(
            product=self.product,
            quantity=1,
            status='pending_payment',
            mpesa_transaction_id='HISTORICAL_RECEIPT',
        )
        response = self.client.post(
            reverse('suppliers:product_delete', args=[self.product.pk]),
        )
        self.assertRedirects(response, reverse('suppliers:product_list'))
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertEqual(order.product, self.product)
        self.assertEqual(order.mpesa_transaction_id, 'HISTORICAL_RECEIPT')
        self.assertFalse(
            RetailProduct.objects.filter(
                pk=self.product.pk,
                is_active=True,
            ).exists()
        )

    def test_supplier_cannot_edit_or_delete_another_supplier_product(self):
        from django.urls import reverse

        edit_response = self.client.get(
            reverse('suppliers:product_edit', args=[self.other_product.pk]),
        )
        delete_response = self.client.post(
            reverse('suppliers:product_delete', args=[self.other_product.pk]),
        )

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(RetailProduct.objects.filter(pk=self.other_product.pk).exists())

    def test_staff_admin_can_edit_product_from_product_management_route(self):
        from django.urls import reverse

        self.client.logout()
        admin_user = get_user_model().objects.create_user(
            username='catalog_admin',
            password='test-password',
            user_type='admin',
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(admin_user)

        admin_change_page = self.client.get(
            reverse('admin:products_product_change', args=[self.other_product.pk]),
        )
        self.assertEqual(admin_change_page.status_code, 200)

        response = self.client.post(
            reverse('products:product_update', args=[self.other_product.pk]),
            self.product_form_data(name='Admin Updated Product'),
        )

        self.assertRedirects(response, reverse('products:product_list'))
        self.other_product.refresh_from_db()
        self.assertEqual(self.other_product.name, 'Admin Updated Product')
        self.assertEqual(self.other_product.supplier, self.other_supplier)

    def test_customer_cannot_create_product(self):
        from django.urls import reverse

        self.client.logout()
        customer = get_user_model().objects.create_user(
            username='catalog_customer',
            password='test-password',
            user_type='customer',
        )
        self.client.force_login(customer)

        response = self.client.post(
            reverse('suppliers:product_create'),
            self.product_form_data(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('accounts:dashboard'))
        self.assertFalse(RetailProduct.objects.filter(name='New VictorMart Product').exists())


class SupplierSubscriptionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username='subscription_supplier',
            password='test-password',
            user_type='supplier',
        )
        self.supplier = Supplier.objects.create(
            user=self.user,
            company_name='Subscription Supplier',
            contact_number='0712345678',
        )
        self.customer = user_model.objects.create_user(
            username='subscription_customer',
            password='test-password',
            user_type='customer',
        )
        self.product = RetailProduct.objects.create(
            name='Subscription Test Phone',
            description='Phone details',
            category='phones',
            cost='10000.00',
            location='Nairobi',
            available_quantity=5,
            supplier=self.supplier,
        )

    def test_supplier_application_offers_supplier_registration(self):
        from django.urls import reverse

        response = self.client.get(reverse('accounts:supplier_application'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'KES 500')
        self.assertContains(response, reverse('accounts:register') + '?role=supplier')

        pricing_response = self.client.get(reverse('accounts:pricing'))
        self.assertEqual(pricing_response.status_code, 200)
        self.assertContains(pricing_response, 'Free Supplier')
        self.assertContains(pricing_response, 'Up to 300 product posts')
        self.assertNotContains(pricing_response, 'Consultant Membership')

        response = self.client.post(
            reverse('accounts:register') + '?role=supplier',
            {
                'username': 'new_supplier',
                'email': 'new-supplier@example.com',
                'role': 'supplier',
                'password1': 'safe-test-password',
                'password2': 'safe-test-password',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('accounts:dashboard'))
        new_user = get_user_model().objects.get(username='new_supplier')
        self.assertEqual(new_user.user_type, 'supplier')
        self.assertTrue(Supplier.objects.filter(user=new_user).exists())

    @patch('apps.orders.mpesa_utils.mpesa_service.initiate_stk_push')
    def test_confirmed_mpesa_callback_activates_premium_for_seven_days(self, initiate_stk_push):
        from django.urls import reverse
        from .models import SupplierSubscriptionPayment

        initiate_stk_push.return_value = {
            'success': True,
            'checkout_request_id': 'SUBSCRIPTION-CHECKOUT-1',
        }
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('suppliers:subscribe_premium'),
            {'phone_number': '0712345678'},
        )
        self.assertEqual(response.status_code, 302)
        payment = SupplierSubscriptionPayment.objects.get(supplier=self.supplier)
        self.assertEqual(payment.status, 'pending')

        response = self.client.post(
            reverse('suppliers:subscription_callback'),
            data=json.dumps({
                'Body': {
                    'stkCallback': {
                        'ResultCode': 0,
                        'CheckoutRequestID': 'SUBSCRIPTION-CHECKOUT-1',
                        'CallbackMetadata': {
                            'Item': [
                                {'Name': 'Amount', 'Value': 500},
                                {'Name': 'MpesaReceiptNumber', 'Value': 'QWE123456'},
                            ],
                        },
                    },
                },
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.supplier.refresh_from_db()
        self.assertEqual(payment.status, 'completed')
        self.assertEqual(payment.receipt_number, 'QWE123456')
        self.assertTrue(self.supplier.is_premium)
        self.assertAlmostEqual(
            (self.supplier.subscription_expires_at - payment.confirmed_at).total_seconds(),
            7 * 24 * 60 * 60,
            delta=1,
        )

    def test_free_supplier_post_cap_is_enforced(self):
        from django.urls import reverse

        RetailProduct.objects.bulk_create([
            RetailProduct(
                name=f'Existing Product {index}',
                description='Already posted',
                category='phones',
                cost='100.00',
                location='Nairobi',
                supplier=self.supplier,
            )
            for index in range(99)
        ])
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('suppliers:product_create'),
            {
                'name': 'Product at quota',
                'description': 'Should be rejected',
                'category': 'phones',
                'cost': '100.00',
                'quality': 'standard',
                'location': 'Nairobi',
                'available_quantity': '1',
                'offer': '',
                'is_active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RetailProduct.objects.filter(name='Product at quota').exists())

    def test_supplier_can_update_whatsapp_contact_number(self):
        from django.urls import reverse

        self.client.force_login(self.user)
        response = self.client.post(
            reverse('suppliers:profile_update'),
            {
                'company_name': 'Updated Shop',
                'location': 'Nairobi',
                'contact_number': '0712345678',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.company_name, 'Updated Shop')
        self.assertEqual(self.supplier.whatsapp_number, '254712345678')

    def test_supplier_dashboard_displays_plan_quota_and_contact_form(self):
        from django.urls import reverse

        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard:supplier_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Free')
        self.assertContains(response, '100')
        self.assertContains(response, 'Pay KES 500 for 7 days')
        self.assertContains(response, 'WhatsApp phone')

    def test_free_product_is_hidden_after_50_unique_customers_view_it(self):
        from django.urls import reverse

        user_model = get_user_model()
        customers = user_model.objects.bulk_create([
            user_model(username=f'weekly_viewer_{index}', user_type='customer')
            for index in range(50)
        ])
        ProductView.objects.bulk_create([
            ProductView(
                product=self.product,
                customer=customer,
                week_start=current_week_start(),
            )
            for customer in customers
        ])

        self.assertNotContains(
            self.client.get(reverse('suppliers:product_list')),
            self.product.name,
        )
        self.assertEqual(
            self.client.get(reverse('suppliers:product_detail', args=[self.product.pk])).status_code,
            404,
        )

    def test_view_limit_resets_for_new_calendar_week_and_premium_bypasses_cap(self):
        from django.urls import reverse

        old_week = current_week_start() - timedelta(days=7)
        user_model = get_user_model()
        customers = user_model.objects.bulk_create([
            user_model(username=f'old_week_viewer_{index}', user_type='customer')
            for index in range(50)
        ])
        ProductView.objects.bulk_create([
            ProductView(
                product=self.product,
                customer=customer,
                week_start=old_week,
            )
            for customer in customers
        ])

        self.client.force_login(self.customer)
        response = self.client.get(reverse('suppliers:product_detail', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ProductView.objects.filter(
            product=self.product,
            customer=self.customer,
            week_start=current_week_start(),
        ).exists())

        self.supplier.subscription_expires_at = timezone.now() + timedelta(days=7)
        self.supplier.save(update_fields=['subscription_expires_at'])
        self.assertEqual(
            self.client.get(reverse('suppliers:product_detail', args=[self.product.pk])).status_code,
            200,
        )

    def test_customer_messaging_is_blocked_for_free_supplier_and_allowed_for_premium(self):
        from django.urls import reverse

        order = Order.objects.create(
            product=self.product,
            customer=self.customer,
            quantity=1,
            status='paid',
        )
        conversation = Conversation.objects.create(
            order=order,
            customer=self.customer,
            supplier=self.user,
        )
        self.client.force_login(self.customer)
        endpoint = reverse('messaging:api_messages', args=[conversation.pk])
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        tracking = self.client.get(reverse('orders:order_tracking', args=[order.pk]))
        self.assertContains(tracking, 'Contact on WhatsApp')
        self.assertNotContains(tracking, 'Message Supplier')

        self.supplier.subscription_expires_at = timezone.now() + timedelta(days=7)
        self.supplier.save(update_fields=['subscription_expires_at'])
        self.assertEqual(self.client.get(endpoint).status_code, 200)
        self.assertContains(
            self.client.get(reverse('orders:order_tracking', args=[order.pk])),
            'View Conversation',
        )
