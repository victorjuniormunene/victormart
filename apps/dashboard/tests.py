from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from apps.orders.models import Order
from apps.products.models import Product
from apps.suppliers.models import Supplier

class DashboardTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='testuser',
            email='test@example.com',
            password='password123',
            first_name='Test',
            last_name='User'
        )
        self.supplier = Supplier.objects.create(
            user=self.user,
            company_name='Test Supplier'
        )
        self.product = Product.objects.create(
            name='Test Product',
            cost=100.00,
            supplier=self.supplier
        )

    def test_customer_dashboard_has_no_consultation_actions(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('dashboard:customer_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Book Consultation')
        self.assertNotContains(response, 'Recent Bookings')

    def test_customer_dashboard_shows_supplier_created_orders(self):
        """Test that supplier-created orders appear in customer dashboard with partial name matching"""
        # Create an order with customer_name that partially matches user's full name
        order = Order.objects.create(
            product=self.product,
            customer=None,  # Supplier-created order
            customer_name='Test User',  # Exact match with full name
            quantity=1
        )

        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('accounts:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(order, response.context['orders'])

    def test_customer_dashboard_shows_orders_with_partial_name_match(self):
        """Test that orders appear with partial name matching"""
        # Create an order with customer_name that is a substring of user's full name
        order = Order.objects.create(
            product=self.product,
            customer=None,
            customer_name='Test',  # Partial match
            quantity=1
        )

        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('accounts:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(order, response.context['orders'])

    def test_customer_dashboard_shows_orders_with_username_match(self):
        """Test that orders appear when customer_name matches username"""
        order = Order.objects.create(
            product=self.product,
            customer=None,
            customer_name='testuser',
            quantity=1
        )

        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('accounts:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(order, response.context['orders'])


class SupplierPaymentDashboardTests(TestCase):
    def test_supplier_dashboard_only_shows_products_owned_by_logged_in_supplier(self):
        user_model = get_user_model()
        supplier_user = user_model.objects.create_user(
            username='isolated_supplier',
            password='test-password',
            user_type='supplier',
        )
        other_user = user_model.objects.create_user(
            username='different_supplier',
            password='test-password',
            user_type='supplier',
        )
        supplier = Supplier.objects.create(
            user=supplier_user,
            company_name='Isolated Supplier',
            location='Nairobi',
        )
        other_supplier = Supplier.objects.create(
            user=other_user,
            company_name='Different Supplier',
            location='Mombasa',
        )
        own_product = Product.objects.create(
            name='My Supplier Listing',
            description='Owned by the logged-in supplier',
            category='phones',
            cost='1000.00',
            location='Nairobi',
            supplier=supplier,
        )
        other_product = Product.objects.create(
            name='Another Supplier Listing',
            description='Owned by a different supplier',
            category='laptops',
            cost='2000.00',
            location='Mombasa',
            supplier=other_supplier,
        )
        self.client.force_login(supplier_user)

        response = self.client.get(reverse('dashboard:supplier_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['products']), [own_product])
        self.assertContains(response, own_product.name)
        self.assertNotContains(response, other_product.name)

    def test_supplier_dashboard_shows_m_pesa_receipts_for_own_products(self):
        user_model = get_user_model()
        supplier_user = user_model.objects.create_user(
            username='payment_supplier',
            password='test-password',
            user_type='supplier',
        )
        customer = user_model.objects.create_user(
            username='payment_customer',
            password='test-password',
            user_type='customer',
        )
        supplier = Supplier.objects.create(
            user=supplier_user,
            company_name='Payment Supplier',
            location='Nairobi',
        )
        product = Product.objects.create(
            name='Payment Test Phone',
            description='Payment test listing',
            category='phones',
            cost='1000.00',
            location='Nairobi',
            available_quantity=5,
            supplier=supplier,
        )
        order = Order.objects.create(
            customer=customer,
            product=product,
            quantity=1,
            status='paid',
            payment_status='completed',
            mpesa_phone_number='254712345678',
            mpesa_transaction_id='TESTRECEIPT1',
            payment_completed_at=timezone.now(),
        )
        product.is_active = False
        product.save(update_fields=['is_active'])
        self.client.force_login(supplier_user)

        response = self.client.get(reverse('dashboard:supplier_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Customer M-Pesa Payments')
        self.assertContains(response, order.order_number)
        self.assertContains(response, 'TESTRECEIPT1')
        self.assertContains(response, '254712345678')
        self.assertContains(response, 'Payment Test Phone')
        self.assertEqual(response.context['mpesa_paid_order_count'], 1)
        self.assertEqual(response.context['mpesa_paid_revenue'], Decimal('1000.00'))
