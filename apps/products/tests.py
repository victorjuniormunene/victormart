from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from .models import Product
from apps.orders.models import Cart, Order
from apps.suppliers.models import Supplier


class RetailCartAndReviewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.customer = user_model.objects.create_user(
            username='retail_customer',
            password='test-password',
            user_type='customer',
        )
        self.seller_user = user_model.objects.create_user(
            username='retail_seller',
            password='test-password',
            user_type='supplier',
        )
        self.supplier = Supplier.objects.create(
            user=self.seller_user,
            company_name='VictorMart Demo Store',
            location='Nairobi',
        )
        self.product = Product.objects.create(
            name='Demo 5G Smartphone',
            description='128GB storage, dual camera and all-day battery.',
            category='phones',
            cost='24999.00',
            quality='premium',
            location='Nairobi',
            available_quantity=3,
            supplier=self.supplier,
        )
        self.construction_product = Product.objects.create(
            name='Cement 50kg',
            description='Construction cement',
            category='cement',
            cost='800.00',
            location='Nairobi',
            available_quantity=10,
            supplier=self.supplier,
        )
        self.client.login(username='retail_customer', password='test-password')

    def test_customer_can_add_in_stock_product_to_cart(self):
        response = self.client.post(
            f'/products/{self.product.pk}/add-to-cart/',
            {'quantity': 2},
        )

        self.assertRedirects(response, f'/products/{self.product.pk}/')
        cart_item = Cart.objects.get(user=self.customer, product=self.product)
        self.assertEqual(cart_item.quantity, 2)

    def test_customer_cannot_add_more_than_available_stock(self):
        response = self.client.post(
            f'/products/{self.product.pk}/add-to-cart/',
            {'quantity': 4},
        )

        self.assertRedirects(response, f'/products/{self.product.pk}/')
        self.assertFalse(Cart.objects.filter(user=self.customer, product=self.product).exists())

    def test_customer_can_review_paid_purchase_once(self):
        order = Order.objects.create(
            customer=self.customer,
            product=self.product,
            quantity=1,
            status='paid',
        )

        response = self.client.post(
            f'/products/{self.product.pk}/review/',
            {'order_id': order.pk, 'rating': 5, 'comment': 'Great phone and fast delivery.'},
        )

        self.assertRedirects(response, f'/products/{self.product.pk}/')
        review = self.product.reviews.get()
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.customer, self.customer)
        self.assertEqual(review.order, order)

    def test_paid_purchase_review_form_is_shown_on_product_page(self):
        Order.objects.create(
            customer=self.customer,
            product=self.product,
            quantity=1,
            status='paid',
        )

        response = self.client.get(f'/products/{self.product.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Submit verified review')

    def test_customer_cannot_review_unpaid_order(self):
        order = Order.objects.create(
            customer=self.customer,
            product=self.product,
            quantity=1,
            status='pending_payment',
        )

        response = self.client.post(
            f'/products/{self.product.pk}/review/',
            {'order_id': order.pk, 'rating': 5, 'comment': 'Not yet purchased.'},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.product.reviews.exists())

    def test_catalog_hides_construction_products(self):
        response = self.client.get('/products/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(response, 'Phones &amp; Tablets')
        self.assertNotContains(response, self.construction_product.name)

    def test_construction_product_detail_is_not_public(self):
        response = self.client.get(f'/products/{self.construction_product.pk}/')

        self.assertEqual(response.status_code, 404)

    def test_archived_product_is_hidden_and_cannot_be_added_to_cart(self):
        self.product.is_active = False
        self.product.save(update_fields=['is_active'])

        list_response = self.client.get('/products/')
        detail_response = self.client.get(f'/products/{self.product.pk}/')
        cart_response = self.client.post(
            f'/products/{self.product.pk}/add-to-cart/',
            {'quantity': 1},
        )

        self.assertNotContains(list_response, self.product.name)
        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(cart_response.status_code, 404)
        self.assertFalse(Cart.objects.filter(user=self.customer, product=self.product).exists())

class ProductModelTest(TestCase):

    def setUp(self):
        user_model = get_user_model()
        seller = user_model.objects.create_user(
            username='product_test_seller',
            password='test-password',
            user_type='supplier',
        )
        supplier = Supplier.objects.create(user=seller, company_name='Test Seller')
        self.product = Product.objects.create(
            name="Test Product",
            description="A product for testing purposes.",
            cost=100.00,
            location="Warehouse A",
            supplier=supplier,
        )

    def test_product_creation(self):
        self.assertEqual(self.product.name, "Test Product")
        self.assertEqual(self.product.description, "A product for testing purposes.")
        self.assertEqual(self.product.cost, 100.00)
        self.assertEqual(self.product.location, "Warehouse A")

    def test_product_str(self):
        self.assertEqual(str(self.product), "Test Product")


class VictorMartCatalogSeedTests(TestCase):
    def test_seed_creates_three_products_per_category_idempotently(self):
        call_command('seed_victormart_products', verbosity=0)
        call_command('seed_victormart_products', verbosity=0)

        products = Product.objects.filter(
            supplier__user__username='victormart_store',
        )
        categories = [key for key, _label in Product.CATEGORY_CHOICES]
        for category in categories:
            with self.subTest(category=category):
                self.assertEqual(products.filter(category=category).count(), 3)
        self.assertEqual(products.count(), 39)
        self.assertFalse(products.filter(image_url__in=[None, '']).exists())
        self.assertFalse(products.filter(description='').exists())
