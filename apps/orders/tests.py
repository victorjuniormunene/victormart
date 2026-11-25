from django.test import TestCase
from unittest.mock import Mock, patch
from .models import Order
from django.contrib.auth import get_user_model
from apps.products.models import Product as CatalogProduct
from apps.suppliers.models import Supplier
from apps.orders.mpesa_utils import mpesa_service

User = get_user_model()

class OrderModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.order = Order.objects.create(
            user=self.user,
            product_name='Concrete',
            quantity=10,
            total_cost=500.00
        )

    def test_order_creation(self):
        self.assertEqual(self.order.user.username, 'testuser')
        self.assertEqual(self.order.product_name, 'Concrete')
        self.assertEqual(self.order.quantity, 10)
        self.assertEqual(self.order.total_cost, 500.00)

    def test_order_str(self):
        self.assertEqual(str(self.order), f'Order {self.order.id} by {self.order.user.username}')

    def test_order_total_cost_calculation(self):
        self.order.quantity = 5
        self.order.total_cost = self.order.quantity * 50.00  # Assuming cost per unit is 50
        self.order.save()
        self.assertEqual(self.order.total_cost, 250.00)

class OrderViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')

    def test_order_list_view(self):
        response = self.client.get('/orders/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/order_list.html')

    def test_order_create_view(self):
        response = self.client.post('/orders/create/', {
            'product_name': 'Steel',
            'quantity': 20,
            'total_cost': 1000.00
        })
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        self.assertTrue(Order.objects.filter(product_name='Steel').exists())


class MpesaOrderCallbackTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.supplier_user = user_model.objects.create_user(
            username='callback_supplier',
            password='test-password',
            user_type='supplier',
        )
        self.customer = user_model.objects.create_user(
            username='callback_customer',
            password='test-password',
            user_type='customer',
        )
        supplier = Supplier.objects.create(
            user=self.supplier_user,
            company_name='Callback Supplier',
        )
        product = CatalogProduct.objects.create(
            name='Callback Phone',
            description='Payment callback test',
            category='phones',
            cost='1000.00',
            location='Nairobi',
            available_quantity=10,
            supplier=supplier,
        )
        self.order = Order.objects.create(
            customer=self.customer,
            product=product,
            quantity=1,
            status='pending_payment',
            mpesa_checkout_request_id='ws_CO_CALLBACK_1',
            mpesa_phone_number='0712345678',
        )

    @patch('apps.orders.mpesa_utils.requests.post')
    @patch('apps.orders.mpesa_utils.requests.get')
    def test_stk_push_uses_oauth_token_and_returns_success(self, mock_get, mock_post):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'access_token': 'test-access-token'},
        )
        mock_post.return_value = Mock(
            status_code=200,
            json=lambda: {
                'CheckoutRequestID': 'ws_CO_STK_TEST',
                'ResponseCode': '0',
                'ResponseDescription': 'Success',
                'CustomerMessage': 'Success. Request accepted for processing',
            },
            text='',
        )

        result = mpesa_service.initiate_stk_push(
            phone_number='0712345678',
            amount=self.order.total_cost,
            order_number=self.order.order_number,
        )

        self.assertTrue(result['success'])
        self.assertEqual(result['checkout_request_id'], 'ws_CO_STK_TEST')
        self.assertEqual(
            mock_post.call_args.kwargs['headers']['Authorization'],
            'Bearer test-access-token',
        )

    def test_successful_callback_records_receipt_for_supplier_dashboard(self):
        callback_data = {
            'Body': {
                'stkCallback': {
                    'ResultCode': 0,
                    'CheckoutRequestID': self.order.mpesa_checkout_request_id,
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'MpesaReceiptNumber', 'Value': 'QAB123XYZ'},
                            {'Name': 'PhoneNumber', 'Value': 254712345678},
                        ],
                    },
                },
            },
        }
        with patch.object(mpesa_service, 'send_payment_notification_email'):
            with patch('apps.orders.views.send_payment_confirmation_email_to_customer'):
                with patch('apps.orders.sms_utils.send_payment_confirmation_sms'):
                    result = mpesa_service.process_callback(callback_data)

        self.assertTrue(result['success'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'completed')
        self.assertEqual(self.order.status, 'paid')
        self.assertEqual(self.order.mpesa_transaction_id, 'QAB123XYZ')
        self.assertEqual(self.order.mpesa_phone_number, '254712345678')
        self.assertIsNotNone(self.order.payment_completed_at)

    def test_failed_bulk_callback_updates_every_order(self):
        second_order = Order.objects.create(
            customer=self.customer,
            product=self.order.product,
            quantity=1,
            status='pending_payment',
            mpesa_checkout_request_id=self.order.mpesa_checkout_request_id,
        )
        callback_data = {
            'Body': {
                'stkCallback': {
                    'ResultCode': 1,
                    'CheckoutRequestID': self.order.mpesa_checkout_request_id,
                    'ResultDesc': 'The customer cancelled the request',
                },
            },
        }

        result = mpesa_service.process_callback(callback_data)

        self.assertFalse(result['success'])
        self.order.refresh_from_db()
        second_order.refresh_from_db()
        self.assertEqual(self.order.payment_status, 'failed')
        self.assertEqual(second_order.payment_status, 'failed')

    def test_customer_can_track_their_order_but_not_another_customers(self):
        other_customer = get_user_model().objects.create_user(
            username='another_customer',
            password='test-password',
            user_type='customer',
        )

        self.client.force_login(self.customer)
        response = self.client.get(
            f'/orders/orders/{self.order.pk}/track/',
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)
        self.assertContains(response, 'Awaiting payment confirmation')

        self.client.force_login(other_customer)
        forbidden_response = self.client.get(
            f'/orders/orders/{self.order.pk}/track/',
        )
        self.assertEqual(forbidden_response.status_code, 404)