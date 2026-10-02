from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import (
    CustomUser,
    Material,
    MaterialCategory,
    UnitOfMeasure,
)
from tarcom.utils.enums import CodeTypes


class ResetPasswordViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/reset-password/'
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='OldPass123!'
        )
        self.code = self.user.create_otp(code_type=CodeTypes.RESET_PASSWORD)

    def test_reset_password_with_code(self):
        data = {
            'email': 'test@example.com',
            'code': self.code,
            'new_password': 'NewStrongPass123!',
            'new_password_confirm': 'NewStrongPass123!',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass123!'))

    def test_reset_password_mismatched_passwords(self):
        data = {
            'email': 'test@example.com',
            'code': self.code,
            'new_password': 'NewStrongPass123!',
            'new_password_confirm': 'DifferentPass123!',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def _reset_payload(self, **extra):
        data = {
            'email': 'test@example.com',
            'new_password': 'NewStrongPass123!',
            'new_password_confirm': 'NewStrongPass123!',
        }
        data.update(extra)
        return data

    def _assert_non_field_error(self, response, message):
        # The custom handler emits bilingual leaves: '{"en": "...", "ar": "..."}'.
        self.assertIn(message, response.data['errors']['non_field_errors'][0])

    def test_reset_password_invalid_token_returns_400(self):
        # Regression: auth.py shadowed DRF's ValidationError with Django's,
        # so this used to escape DRF and surface as a 500.
        response = self.client.post(
            self.url, self._reset_payload(reset_token='not-a-real-token'), format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_non_field_error(response, 'Invalid or expired reset token.')

    def test_reset_password_token_email_mismatch_returns_400(self):
        from django.core.signing import TimestampSigner

        response = self.client.post(
            self.url,
            self._reset_payload(reset_token=TimestampSigner().sign('other@example.com')),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_non_field_error(response, 'Token does not match email.')

    def test_reset_password_unknown_otp_returns_400(self):
        response = self.client.post(self.url, self._reset_payload(code=999999), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self._assert_non_field_error(response, 'Invalid or already used OTP code.')

class UnitOfMeasureAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = CustomUser.objects.create_superuser(
            email='admin@tarcom.com', password='AdminPass123!'
        )
        self.uom = UnitOfMeasure.objects.create(
            name='Piece',
            name_en='Piece',
            name_ar='قطعة',
            code='PCS'
        )

    def test_unauthenticated_can_list_units(self):
        response = self.client.get('/api/units/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_unauthenticated_cannot_create_unit(self):
        data = {'name_en': 'Box', 'name_ar': 'صندوق', 'code': 'BOX'}
        response = self.client.post('/api/units/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_create_unit_with_translation(self):
        self.client.force_authenticate(user=self.admin_user)
        data = {'name_en': 'Kilogram', 'name_ar': 'كيلوجرام', 'code': 'KG'}
        response = self.client.post('/api/units/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 'KG')
        self.assertEqual(response.data['name_en'], 'Kilogram')
        self.assertEqual(response.data['name_ar'], 'كيلوجرام')

    def test_unit_translation_header(self):
        # With Arabic header
        res_ar = self.client.get(f'/api/units/{self.uom.id}/', HTTP_ACCEPT_LANGUAGE='ar')
        self.assertEqual(res_ar.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ar.data['name'], 'قطعة')
        self.assertEqual(res_ar.data['name_en'], 'Piece')
        self.assertEqual(res_ar.data['name_ar'], 'قطعة')

        # With English header
        res_en = self.client.get(f'/api/units/{self.uom.id}/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(res_en.status_code, status.HTTP_200_OK)
        self.assertEqual(res_en.data['name'], 'Piece')

    def test_uoms_alias_route_is_removed(self):
        for url in (f'/api/uoms/{self.uom.id}/', '/api/uoms/'):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class MaterialCategoryAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = CustomUser.objects.create_superuser(
            email='admin@tarcom.com', password='AdminPass123!'
        )
        self.parent_cat = MaterialCategory.objects.create(
            name='Electronics',
            name_en='Electronics',
            name_ar='إلكترونيات',
        )

    def test_admin_can_create_category_with_translation(self):
        self.client.force_authenticate(user=self.admin_user)
        data = {
            'name_en': 'Smartphones',
            'name_ar': 'هواتف ذكية',
            'parent': self.parent_cat.id,
        }
        response = self.client.post('/api/categories/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name_en'], 'Smartphones')
        self.assertEqual(response.data['name_ar'], 'هواتف ذكية')
        self.assertEqual(response.data['parent'], self.parent_cat.id)

    def test_category_tree_action(self):
        MaterialCategory.objects.create(
            name='Laptops',
            name_en='Laptops',
            name_ar='حواسيب محمولة',
            parent=self.parent_cat
        )
        response = self.client.get('/api/categories/tree/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name_en'], 'Electronics')
        self.assertEqual(len(response.data[0]['subcategories']), 1)
        self.assertEqual(response.data[0]['subcategories'][0]['name_en'], 'Laptops')

    def test_category_translation_header(self):
        res_ar = self.client.get(f'/api/categories/{self.parent_cat.id}/', HTTP_ACCEPT_LANGUAGE='ar')
        self.assertEqual(res_ar.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ar.data['name'], 'إلكترونيات')

        res_en = self.client.get(f'/api/categories/{self.parent_cat.id}/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(res_en.status_code, status.HTTP_200_OK)
        self.assertEqual(res_en.data['name'], 'Electronics')

class MaterialAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = CustomUser.objects.create_superuser(
            email='admin@tarcom.com', password='AdminPass123!'
        )
        self.uom = UnitOfMeasure.objects.create(
            name='Piece', name_en='Piece', name_ar='قطعة', code='PCS'
        )
        self.category = MaterialCategory.objects.create(
            name='Devices', name_en='Devices', name_ar='أجهزة'
        )
        self.material = Material.objects.create(
            name='Phone',
            name_en='Phone',
            name_ar='هاتف',
            description='Smart device',
            description_en='Smart device',
            description_ar='جهاز ذكي',
            category=self.category,
            uom=self.uom,
            supplier_price=500.00,
            consumer_price=700.00,
            is_active=True,
        )

    def test_list_materials(self):
        res_materials = self.client.get('/api/materials/')
        self.assertEqual(res_materials.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_materials.data), 1)
        self.assertEqual(res_materials.data[0]['category_name'], 'Devices')
        self.assertEqual(res_materials.data[0]['uom_name'], 'Piece')

    def test_products_alias_route_is_removed(self):
        for url in (f'/api/products/{self.material.id}/', '/api/products/'):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_create_material_with_translations(self):
        self.client.force_authenticate(user=self.admin_user)
        data = {
            'name_en': 'Tablet',
            'name_ar': 'لوحي',
            'description_en': 'Screen 10 inch',
            'description_ar': 'شاشة 10 بوصة',
            'category': self.category.id,
            'uom': self.uom.id,
            'supplier_price': '300.00',
            'consumer_price': '450.00',
            'is_active': True,
        }
        response = self.client.post('/api/materials/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name_en'], 'Tablet')
        self.assertEqual(response.data['name_ar'], 'لوحي')
        self.assertEqual(response.data['description_en'], 'Screen 10 inch')
        self.assertEqual(response.data['description_ar'], 'شاشة 10 بوصة')

    def test_material_translation_by_header(self):
        res_ar = self.client.get(f'/api/materials/{self.material.id}/', HTTP_ACCEPT_LANGUAGE='ar')
        self.assertEqual(res_ar.status_code, status.HTTP_200_OK)
        self.assertEqual(res_ar.data['name'], 'هاتف')
        self.assertEqual(res_ar.data['description'], 'جهاز ذكي')

        res_en = self.client.get(f'/api/materials/{self.material.id}/', HTTP_ACCEPT_LANGUAGE='en')
        self.assertEqual(res_en.status_code, status.HTTP_200_OK)
        self.assertEqual(res_en.data['name'], 'Phone')
        self.assertEqual(res_en.data['description'], 'Smart device')

    def test_filter_materials(self):
        other_cat = MaterialCategory.objects.create(name='Clothing', name_en='Clothing', name_ar='ملابس')
        res_filtered = self.client.get(f'/api/materials/?category={other_cat.id}')
        self.assertEqual(res_filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_filtered.data), 0)

        res_active = self.client.get('/api/materials/?is_active=true')
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_active.data), 1)

    def test_admin_update_material(self):
        self.client.force_authenticate(user=self.admin_user)
        data = {'consumer_price': '750.00', 'name_en': 'Phone Pro'}
        response = self.client.patch(f'/api/materials/{self.material.id}/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['consumer_price'], '750.00')
        self.assertEqual(response.data['name_en'], 'Phone Pro')

    def test_unauthenticated_cannot_delete_material(self):
        response = self.client.delete(f'/api/materials/{self.material.id}/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

# ==========================================
# OpenAPI schema / docs endpoints
# ==========================================

class OpenAPISchemaTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_schema_endpoint_returns_200(self):
        response = self.client.get('/api/schema/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('openapi', response.content.decode())

    def test_swagger_ui_returns_200(self):
        response = self.client.get('/api/docs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_redoc_returns_200(self):
        response = self.client.get('/api/redoc/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

