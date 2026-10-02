"""Contract tests for the django_filters-backed list endpoints.

These pin the behaviour that replaced ``rest_framework.filters``:
``?search=`` (one ``icontains`` per field, OR'd), ``?ordering=`` (CSV, ``-`` for
descending), case-insensitive enum values, and HTTP 400 — not 500 — for
malformed query values.
"""

import ast
import os
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import (
    CustomUser,
    FavouriteItem,
    Material,
    MaterialCategory,
    Order,
    Setting,
    UnitOfMeasure,
)
from tarcom.utils.enums import OrderStatus, PaymentStatus


class RestFrameworkFiltersBanTest(TestCase):
    """Guard the architectural rule: only django_filters may filter the API."""

    def test_no_module_imports_rest_framework_filters(self):
        api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for root, dirs, files in os.walk(api_dir):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for filename in files:
                if not filename.endswith('.py'):
                    continue
                path = os.path.join(root, filename)
                with open(path, encoding='utf-8') as handle:
                    tree = ast.parse(handle.read(), filename=path)
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.Import, ast.ImportFrom)):
                        continue
                    if isinstance(node, ast.ImportFrom):
                        if (node.module or '').startswith('rest_framework.filters') or node.module == 'rest_framework' and any(
                            alias.name == 'filters' for alias in node.names
                        ):
                            offenders.append(path)
                    elif any(alias.name.startswith('rest_framework.filters') for alias in node.names):
                        offenders.append(path)
        self.assertEqual(offenders, [])


class OrderListFilterTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = CustomUser.objects.create_user(
            email='customer@example.com', password='StrongPass123!', is_verified=True
        )
        self.other_customer = CustomUser.objects.create_user(
            email='other@example.com', password='StrongPass123!', is_verified=True
        )
        self.admin = CustomUser.objects.create_superuser(
            email='admin@tarcom.com', password='AdminPass123!'
        )
        self.category = MaterialCategory.objects.create(name='Steel')
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.material = Material.objects.create(
            name='Steel Rod', category=self.category, uom=self.uom,
            consumer_price=Decimal('100.00'), is_active=True,
        )
        self.url = '/api/orders/'

    def place_order(self, user, phone, quantity='1.000'):
        self.client.force_authenticate(user=user)
        response = self.client.post(self.url, {
            'payment_method': 'CASH',
            'shipping_address': 'Amman, Jordan',
            'shipping_phone': phone,
            'items': [{'material': self.material.id, 'quantity': quantity}],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return response.data

    def assertRejected(self, query, field):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'{self.url}?{query}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data['code'], status.HTTP_400_BAD_REQUEST)
        self.assertIn(field, response.data['errors'])

    def test_search_matches_order_number_phone_and_email(self):
        own = self.place_order(self.customer, '+963911111111')
        self.place_order(self.other_customer, '+963922222222')
        self.client.force_authenticate(user=self.admin)

        by_phone = self.client.get(f'{self.url}?search=911111')
        self.assertEqual(by_phone.status_code, status.HTTP_200_OK)
        self.assertEqual([o['id'] for o in by_phone.data], [own['id']])

        by_email = self.client.get(f'{self.url}?search=other@example.com')
        self.assertEqual(by_email.status_code, status.HTTP_200_OK)
        self.assertEqual(len(by_email.data), 1)
        self.assertNotEqual(by_email.data[0]['id'], own['id'])

        by_number = self.client.get(f'{self.url}?search={own["order_number"]}')
        self.assertEqual(by_number.status_code, status.HTTP_200_OK)
        self.assertEqual([o['id'] for o in by_number.data], [own['id']])

        none = self.client.get(f'{self.url}?search=no-such-term')
        self.assertEqual(none.status_code, status.HTTP_200_OK)
        self.assertEqual(none.data, [])

    def test_status_filter_is_case_insensitive(self):
        pending = self.place_order(self.customer, '+963911111111')
        shipped = self.place_order(self.customer, '+963911111112')
        Order.objects.filter(pk=shipped['id']).update(status=OrderStatus.SHIPPED)
        self.client.force_authenticate(user=self.customer)

        for value in ('pending', 'PENDING', 'Pending'):
            response = self.client.get(f'{self.url}?status={value}')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual([o['id'] for o in response.data], [pending['id']], value)

        response = self.client.get(f'{self.url}?status=shipped')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([o['id'] for o in response.data], [shipped['id']])

    def test_payment_status_filter_is_case_insensitive(self):
        order = self.place_order(self.customer, '+963911111111')
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(f'{self.url}?payment_status=unpaid')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([o['id'] for o in response.data], [order['id']])

        Order.objects.filter(pk=order['id']).update(payment_status=PaymentStatus.PAID)
        response = self.client.get(f'{self.url}?payment_status=PAID')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([o['id'] for o in response.data], [order['id']])

    def test_unknown_enum_values_are_rejected(self):
        self.place_order(self.customer, '+963911111111')
        self.assertRejected('status=bogus', 'status')
        self.assertRejected('payment_status=bogus', 'payment_status')

    def test_ordering_by_total_amount(self):
        cheap = self.place_order(self.customer, '+963911111111', quantity='1.000')
        pricey = self.place_order(self.customer, '+963911111112', quantity='5.000')
        self.client.force_authenticate(user=self.customer)

        ascending = self.client.get(f'{self.url}?ordering=total_amount')
        self.assertEqual([o['id'] for o in ascending.data], [cheap['id'], pricey['id']])

        descending = self.client.get(f'{self.url}?ordering=-total_amount')
        self.assertEqual([o['id'] for o in descending.data], [pricey['id'], cheap['id']])

    def test_unknown_ordering_field_is_rejected(self):
        self.place_order(self.customer, '+963911111111')
        self.assertRejected('ordering=bogus', 'ordering')

    def test_csv_ordering_is_applied_left_to_right(self):
        self.place_order(self.customer, '+963911111111')
        self.place_order(self.customer, '+963911111112')
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(f'{self.url}?ordering=-created_at,total_amount')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 2)

    def test_default_ordering_is_newest_first(self):
        older = self.place_order(self.customer, '+963911111111')
        newer = self.place_order(self.customer, '+963911111112')
        Order.objects.filter(pk=older['id']).update(
            created_at=Order.objects.get(pk=older['id']).created_at.replace(year=2020)
        )
        self.client.force_authenticate(user=self.customer)

        response = self.client.get(self.url)
        self.assertEqual([o['id'] for o in response.data], [newer['id'], older['id']])


class CategoryListFilterTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.root = MaterialCategory.objects.create(name='Electronics')
        self.child = MaterialCategory.objects.create(name='Phones')
        self.other_root = MaterialCategory.objects.create(name='Clothing')
        self.url = '/api/categories/'

    def test_search_and_ordering(self):
        by_name = self.client.get(f'{self.url}?search=Phones')
        self.assertEqual([c['id'] for c in by_name.data], [self.child.id])

        ascending = self.client.get(f'{self.url}?ordering=name')
        self.assertEqual(
            [c['name'] for c in ascending.data], ['Clothing', 'Electronics', 'Phones']
        )

        descending = self.client.get(f'{self.url}?ordering=-name')
        self.assertEqual(
            [c['name'] for c in descending.data], ['Phones', 'Electronics', 'Clothing']
        )


class MaterialListFilterTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = MaterialCategory.objects.create(name='Devices')
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.cheap = Material.objects.create(
            name='Basic Phone', category=self.category, uom=self.uom,
            consumer_price=Decimal('50.00'), is_active=True,
        )
        self.pricey = Material.objects.create(
            name='Fancy Phone', category=self.category, uom=self.uom,
            consumer_price=Decimal('900.00'), is_active=True,
        )
        self.retired = Material.objects.create(
            name='Old Phone', category=self.category, uom=self.uom,
            consumer_price=Decimal('10.00'), is_active=False,
        )
        self.url = '/api/materials/'

    def test_search_and_is_active(self):
        found = self.client.get(f'{self.url}?search=Fancy')
        self.assertEqual([m['id'] for m in found.data], [self.pricey.id])

        inactive = self.client.get(f'{self.url}?is_active=false')
        self.assertEqual([m['id'] for m in inactive.data], [self.retired.id])

        active = self.client.get(f'{self.url}?is_active=true')
        self.assertEqual({m['id'] for m in active.data}, {self.cheap.id, self.pricey.id})

    def test_ordering_by_consumer_price(self):
        ascending = self.client.get(f'{self.url}?ordering=consumer_price')
        self.assertEqual(
            [m['id'] for m in ascending.data],
            [self.retired.id, self.cheap.id, self.pricey.id],
        )

        descending = self.client.get(f'{self.url}?ordering=-consumer_price')
        self.assertEqual(
            [m['id'] for m in descending.data],
            [self.pricey.id, self.cheap.id, self.retired.id],
        )

    def test_malformed_category_is_rejected_with_400(self):
        response = self.client.get(f'{self.url}?category=abc')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('category', response.data['errors'])

    def test_spec_key_value_pair_matches_within_the_same_slot(self):
        # RAM sits in different slots on purpose: a (spec_keyN, spec_valN) pair
        # must match key and value on the *same* slot, not independently.
        Material.objects.filter(pk=self.cheap.pk).update(spec_key3='RAM', spec_val3='16GB')
        Material.objects.filter(pk=self.pricey.pk).update(spec_key1='RAM', spec_val1='12GB')
        Material.objects.filter(pk=self.retired.pk).update(spec_key2='Storage', spec_val2='512GB')

        paired = self.client.get(f'{self.url}?spec_key1=RAM&spec_val1=12')
        self.assertEqual([m['id'] for m in paired.data], [self.pricey.id])

        mismatched = self.client.get(f'{self.url}?spec_key1=RAM&spec_val1=99')
        self.assertEqual(mismatched.data, [])

    def test_spec_key_alone_matches_any_slot(self):
        Material.objects.filter(pk=self.cheap.pk).update(spec_key3='RAM', spec_val3='16GB')
        Material.objects.filter(pk=self.pricey.pk).update(spec_key1='RAM', spec_val1='12GB')
        Material.objects.filter(pk=self.retired.pk).update(spec_key2='Storage', spec_val2='512GB')

        by_key = self.client.get(f'{self.url}?spec_key2=RAM')
        self.assertEqual({m['id'] for m in by_key.data}, {self.cheap.id, self.pricey.id})

    def test_spec_val_alone_matches_any_slot(self):
        Material.objects.filter(pk=self.retired.pk).update(spec_key2='Storage', spec_val2='512GB')

        by_val = self.client.get(f'{self.url}?spec_val3=512')
        self.assertEqual([m['id'] for m in by_val.data], [self.retired.id])

    def test_spec_filters_combine_with_category(self):
        other = MaterialCategory.objects.create(name='Clothing')
        laptop = Material.objects.create(
            name='Laptop', category=self.category, uom=self.uom,
            consumer_price=Decimal('1200.00'), is_active=True,
            spec_key1='RAM', spec_val1='12GB',
        )
        Material.objects.create(
            name='Shirt', category=other, uom=self.uom,
            consumer_price=Decimal('20.00'), is_active=True,
            spec_key1='RAM', spec_val1='12GB',
        )

        response = self.client.get(
            f'{self.url}?category={self.category.id}&spec_key1=RAM&spec_val1=12'
        )
        self.assertEqual([m['id'] for m in response.data], [laptop.id])


class UnitAndSettingFilterTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.kg = UnitOfMeasure.objects.create(name='Kilogram', code='KG')
        self.pc = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.setting = Setting.objects.create(key='SITE_NAME', value='Tarcom')
        self.other_setting = Setting.objects.create(key='SUPPORT_PHONE', value='069000')

    def test_units_search_and_ordering(self):
        found = self.client.get('/api/units/?search=KG')
        self.assertEqual([u['id'] for u in found.data], [self.kg.id])

        ascending = self.client.get('/api/units/?ordering=code')
        self.assertEqual([u['code'] for u in ascending.data], ['KG', 'PCS'])

        descending = self.client.get('/api/units/?ordering=-code')
        self.assertEqual([u['code'] for u in descending.data], ['PCS', 'KG'])

    def test_settings_search_and_ordering(self):
        # `SettingsViewSet` declared search_fields/ordering_fields but had no
        # filter backends, so neither parameter ever reached the endpoint.
        found = self.client.get('/api/settings/?search=SITE_NAME')
        self.assertEqual([s['key'] for s in found.data], ['SITE_NAME'])

        ascending = self.client.get('/api/settings/?ordering=key')
        self.assertEqual(
            [s['key'] for s in ascending.data], ['SITE_NAME', 'SUPPORT_PHONE']
        )

        descending = self.client.get('/api/settings/?ordering=-key')
        self.assertEqual(
            [s['key'] for s in descending.data], ['SUPPORT_PHONE', 'SITE_NAME']
        )


class FavouriteListFilterTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='customer@example.com', password='StrongPass123!', is_verified=True
        )
        self.category = MaterialCategory.objects.create(name='Tools')
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.hammer = Material.objects.create(
            name='Hammer', category=self.category, uom=self.uom, is_active=True
        )
        self.saw = Material.objects.create(
            name='Saw Blade', category=self.category, uom=self.uom, is_active=True
        )
        self.url = '/api/favourites/'
        self.client.force_authenticate(user=self.user)

    def test_name_filters_by_material_name(self):
        first = FavouriteItem.objects.create(user=self.user, material=self.hammer)
        FavouriteItem.objects.create(user=self.user, material=self.saw)

        response = self.client.get(f'{self.url}?name=hammer')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([f['id'] for f in response.data], [first.id])

    def test_default_ordering_is_newest_first(self):
        older = FavouriteItem.objects.create(user=self.user, material=self.hammer)
        newer = FavouriteItem.objects.create(user=self.user, material=self.saw)
        FavouriteItem.objects.filter(pk=older.pk).update(
            created_at=older.created_at.replace(year=2020)
        )

        response = self.client.get(self.url)
        self.assertEqual([f['id'] for f in response.data], [newer.id, older.id])

    def test_ordering_ascending_by_created_at(self):
        older = FavouriteItem.objects.create(user=self.user, material=self.hammer)
        newer = FavouriteItem.objects.create(user=self.user, material=self.saw)
        FavouriteItem.objects.filter(pk=older.pk).update(
            created_at=older.created_at.replace(year=2020)
        )

        response = self.client.get(f'{self.url}?ordering=created_at')
        self.assertEqual([f['id'] for f in response.data], [older.id, newer.id])
