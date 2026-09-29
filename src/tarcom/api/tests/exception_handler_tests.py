import json

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.exceptions import MethodNotAllowed, NotAuthenticated, ValidationError
from rest_framework.test import APIClient

from tarcom.base.models import CustomUser, Material, MaterialCategory, OTPCode, Order, UnitOfMeasure
from tarcom.utils.enums import CodeTypes, OrderStatus
from tarcom.utils.exceptions import custom_exception_handler

ENVELOPE_KEYS = {'status', 'code', 'message', 'errors'}


def assert_envelope(testcase, response, expected_status):
    testcase.assertEqual(response.status_code, expected_status)
    testcase.assertEqual(set(response.data.keys()), ENVELOPE_KEYS)
    testcase.assertEqual(response.data['status'], 'error')
    testcase.assertEqual(response.data['code'], expected_status)
    testcase.assertIsInstance(response.data['message'], str)
    parsed = json.loads(response.data['message'])
    testcase.assertIsInstance(parsed, dict)
    testcase.assertIn('en', parsed)
    testcase.assertIn('ar', parsed)
    testcase.assertIn('errors', response.data)


class CustomExceptionHandlerTest(TestCase):
    def test_validation_error_envelope(self):
        exc = ValidationError({'email': ['This field is required.']})
        response = custom_exception_handler(exc, None)
        assert_envelope(self, response, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data['errors'])
        self.assertIn('This field is required.', response.data['errors']['email'][0])

    def test_not_authenticated_envelope(self):
        response = custom_exception_handler(NotAuthenticated(), None)
        assert_envelope(self, response, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data['errors'])

    def test_method_not_allowed_envelope(self):
        response = custom_exception_handler(MethodNotAllowed('DELETE'), None)
        assert_envelope(self, response, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_unhandled_exception_returns_500_envelope(self):
        response = custom_exception_handler(ValueError('boom'), None)
        assert_envelope(self, response, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['errors'], {})


class ApiErrorResponseEnvelopeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='buyer@example.com', password='StrongPass123!', is_verified=True
        )
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.category = MaterialCategory.objects.create(name='Steel')
        self.material = Material.objects.create(
            name='Steel Rod', category=self.category, uom=self.uom,
            consumer_price=Decimal('100.00'), is_active=True,
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def test_login_validation_error_envelope(self):
        response = self.client.post('/api/auth/login/', {'email': ''}, format='json')
        assert_envelope(self, response, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data['errors'])

    def test_unauthenticated_request_envelope(self):
        response = self.client.get('/api/orders/')
        assert_envelope(self, response, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data['errors'])

    def test_method_not_allowed_envelope(self):
        response = self.client.get('/api/auth/login/')
        assert_envelope(self, response, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_converted_toggle_missing_material_envelope(self):
        self.authenticate()
        response = self.client.post('/api/favourites/toggle/', {}, format='json')
        assert_envelope(self, response, status.HTTP_400_BAD_REQUEST)
        self.assertIn('material field is required.', response.data['message'])

    def test_converted_check_missing_param_envelope(self):
        self.authenticate()
        response = self.client.get('/api/favourites/check/')
        assert_envelope(self, response, status.HTTP_400_BAD_REQUEST)
        self.assertIn('material parameter is required.', response.data['message'])

    def test_converted_remove_by_material_404_envelope(self):
        self.authenticate()
        response = self.client.delete('/api/favourites/remove-by-material/999999/')
        assert_envelope(self, response, status.HTTP_404_NOT_FOUND)
        self.assertIn('detail', response.data['errors'])
        self.assertIn('Material is not in favourites.', response.data['errors']['detail'][0])

    def test_converted_forget_password_throttle_envelope(self):
        for _ in range(5):
            OTPCode.objects.create(email='buyer@example.com', code_type=CodeTypes.RESET_PASSWORD)
        response = self.client.post('/api/auth/forget-password/', {'email': 'buyer@example.com'}, format='json')
        assert_envelope(self, response, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn('Too many requests. Please try again later.', response.data['message'])

    def test_converted_order_cancel_envelope(self):
        self.authenticate()
        payload = {
            'payment_method': 'CASH',
            'shipping_address': 'Amman, Jordan',
            'shipping_phone': '0791234567',
            'items': [{'material': self.material.id, 'quantity': '2.000'}],
        }
        created = self.client.post('/api/orders/', payload, format='json')
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        Order.objects.filter(id=created.data['id']).update(status=OrderStatus.SHIPPED)

        response = self.client.post(f"/api/orders/{created.data['id']}/cancel/")
        assert_envelope(self, response, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Orders can only be cancelled while in PENDING status.', response.data['message'])
