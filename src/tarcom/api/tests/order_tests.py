from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import (
    CustomUser,
    Material,
    MaterialCategory,
    Order,
    UnitOfMeasure,
)
from tarcom.utils.enums import OrderStatus, PaymentStatus


class OrderAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = CustomUser.objects.create_user(
            email='customer@example.com',
            password='StrongPass123!',
            first_name='Buy',
            last_name='Er',
            is_verified=True,
        )
        self.other_customer = CustomUser.objects.create_user(
            email='other@example.com', password='StrongPass123!', is_verified=True
        )
        self.admin = CustomUser.objects.create_superuser(
            email='admin@tarcom.com', password='AdminPass123!'
        )
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.category = MaterialCategory.objects.create(name='Steel')
        self.material1 = Material.objects.create(
            name='Steel Rod', category=self.category, uom=self.uom,
            consumer_price=Decimal('100.00'), is_active=True,
        )
        self.material2 = Material.objects.create(
            name='Steel Sheet', category=self.category, uom=self.uom,
            consumer_price=Decimal('50.00'), is_active=True,
        )
        self.inactive_material = Material.objects.create(
            name='Discontinued', category=self.category, uom=self.uom,
            consumer_price=Decimal('10.00'), is_active=False,
        )
        self.url = '/api/orders/'

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.customer)

    def place_order(self, user=None, items=None):
        self.authenticate(user or self.customer)
        payload = {
            'payment_method': 'CASH',
            'shipping_address': 'Amman, Jordan',
            'shipping_phone': '+963912345678',
            'items': items or [
                {'material': self.material1.id, 'quantity': '2.000'},
                {'material': self.material2.id, 'quantity': '3.000'},
            ],
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response

    # ---------------------------------------------
    # Checkout / creation
    # ---------------------------------------------

    def test_create_order_success(self):
        response = self.place_order()
        data = response.data

        self.assertTrue(data['order_number'].startswith('ORD-'))
        self.assertEqual(data['status'], OrderStatus.PENDING)
        self.assertEqual(data['payment_status'], PaymentStatus.UNPAID)
        self.assertEqual(len(data['items']), 2)

        line_totals = {item['material']: item['line_total'] for item in data['items']}
        self.assertEqual(Decimal(line_totals[self.material1.id]), Decimal('200.00'))
        self.assertEqual(Decimal(line_totals[self.material2.id]), Decimal('150.00'))

        self.assertEqual(Decimal(data['subtotal']), Decimal('350.00'))
        self.assertEqual(Decimal(data['total_amount']), Decimal('350.00'))

        order = Order.objects.get(id=data['id'])
        self.assertEqual(order.user, self.customer)
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.subtotal, Decimal('350.00'))

    def test_create_order_empty_items_fails(self):
        self.authenticate()
        response = self.client.post(
            self.url,
            {'payment_method': 'CASH', 'items': []},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    def test_create_order_inactive_material_fails(self):
        self.authenticate()
        response = self.client.post(
            self.url,
            {'payment_method': 'CASH', 'items': [{'material': self.inactive_material.id, 'quantity': '1.000'}]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    def test_create_order_duplicate_materials_fails(self):
        self.authenticate()
        response = self.client.post(
            self.url,
            {
                'payment_method': 'CASH',
                'items': [
                    {'material': self.material1.id, 'quantity': '1.000'},
                    {'material': self.material1.id, 'quantity': '2.000'},
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)

    # ---------------------------------------------
    # Visibility
    # ---------------------------------------------

    def test_customer_can_only_see_own_orders(self):
        own = self.place_order().data
        self.place_order(user=self.other_customer, items=[{'material': self.material2.id, 'quantity': '1.000'}])

        self.authenticate()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], own['id'])

        other_order = Order.objects.filter(user=self.other_customer).first()
        detail = self.client.get(f'{self.url}{other_order.id}/')
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_see_all_orders(self):
        self.place_order()
        self.place_order(user=self.other_customer, items=[{'material': self.material2.id, 'quantity': '1.000'}])

        self.authenticate(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_unauthenticated_cannot_access_orders(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, status.HTTP_401_UNAUTHORIZED)

    # ---------------------------------------------
    # Cancellation
    # ---------------------------------------------

    def test_customer_cancel_pending_order(self):
        order_id = self.place_order().data['id']

        self.authenticate()
        response = self.client.post(f'{self.url}{order_id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_customer_cannot_cancel_shipped_order(self):
        order_id = self.place_order().data['id']
        Order.objects.filter(id=order_id).update(status=OrderStatus.SHIPPED)

        self.authenticate()
        response = self.client.post(f'{self.url}{order_id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, OrderStatus.SHIPPED)

    # ---------------------------------------------
    # Admin status transitions
    # ---------------------------------------------

    def test_admin_update_order_status(self):
        order_id = self.place_order().data['id']

        self.authenticate(self.admin)
        response = self.client.patch(
            f'{self.url}{order_id}/status/',
            {'status': OrderStatus.SHIPPED, 'payment_status': PaymentStatus.PAID},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], OrderStatus.SHIPPED)
        self.assertEqual(response.data['payment_status'], PaymentStatus.PAID)

        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, OrderStatus.SHIPPED)
        self.assertEqual(order.payment_status, PaymentStatus.PAID)

    def test_customer_cannot_update_order_status(self):
        order_id = self.place_order().data['id']

        self.authenticate()
        response = self.client.patch(
            f'{self.url}{order_id}/status/',
            {'status': OrderStatus.SHIPPED},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.status, OrderStatus.PENDING)

    def test_status_update_requires_at_least_one_field(self):
        order_id = self.place_order().data['id']

        self.authenticate(self.admin)
        response = self.client.patch(f'{self.url}{order_id}/status/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # payment_status alone is accepted
        response = self.client.patch(
            f'{self.url}{order_id}/status/',
            {'payment_status': PaymentStatus.PAID},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.payment_status, PaymentStatus.PAID)
        self.assertEqual(order.status, OrderStatus.PENDING)

    # ---------------------------------------------
    # Listing / detail serializers
    # ---------------------------------------------

    def test_order_list_includes_items_count(self):
        self.place_order()
        self.authenticate()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['items_count'], 2)

    def test_order_detail_includes_item_lines(self):
        order_id = self.place_order().data['id']
        self.authenticate()
        response = self.client.get(f'{self.url}{order_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data['items'][0]
        self.assertIn('material_name', item)
        self.assertIn('uom_code', item)
        self.assertEqual(Decimal(item['line_total']), Decimal('200.00'))
