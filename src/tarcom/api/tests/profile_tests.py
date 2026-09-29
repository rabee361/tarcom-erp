import io
import os
import shutil
import tempfile

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import CustomUser

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix='tarcom_test_media_')


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


def image_bytes(fmt='PNG', size=(8, 8)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color=(200, 30, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


def oversized_image_bytes():
    # Random noise does not compress, so the PNG is reliably larger than 2MB.
    buffer = io.BytesIO()
    noise = Image.frombytes('RGB', (900, 900), os.urandom(900 * 900 * 3))
    noise.save(buffer, format='PNG')
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class ProfileAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='user@example.com',
            password='StrongPass123!',
            first_name='Old',
            last_name='Name',
            is_verified=True,
        )
        self.url = '/api/users/me/'

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    # ---------------------------------------------
    # Read / update profile
    # ---------------------------------------------

    def test_get_profile_authenticated(self):
        self.authenticate()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'user@example.com')
        self.assertEqual(response.data['first_name'], 'Old')

    def test_get_profile_unauthenticated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_patch_profile(self):
        self.authenticate()
        data = {'first_name': 'New', 'last_name': 'Person', 'phone': '0791234567'}
        response = self.client.patch(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.last_name, 'Person')
        self.assertEqual(self.user.phone, '0791234567')

    def test_put_profile(self):
        self.authenticate()
        data = {'first_name': 'Replaced', 'last_name': 'Entirely', 'phone': '0790000000'}
        response = self.client.put(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Replaced')
        self.assertEqual(self.user.phone, '0790000000')

    # ---------------------------------------------
    # Avatar validation
    # ---------------------------------------------

    def test_patch_profile_avatar_validation(self):
        self.authenticate()

        # Valid PNG upload succeeds.
        valid = SimpleUploadedFile('avatar.png', image_bytes(), content_type='image/png')
        response = self.client.patch(self.url, {'avatar': valid}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)

        # File larger than 2MB is rejected.
        too_big = SimpleUploadedFile('big.png', oversized_image_bytes(), content_type='image/png')
        response = self.client.patch(self.url, {'avatar': too_big}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Disallowed extension is rejected (even with valid image content).
        bad_ext = SimpleUploadedFile('payload.exe', image_bytes(), content_type='application/octet-stream')
        response = self.client.patch(self.url, {'avatar': bad_ext}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.endswith('.png'), self.user.avatar.name)
        self.assertIn('avatar', self.user.avatar.name)

    def test_delete_avatar(self):
        self.authenticate()
        self.user.avatar.save(
            'avatar.png', content=SimpleUploadedFile('avatar.png', image_bytes()), save=True
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)

        response = self.client.delete('/api/users/me/avatar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    # ---------------------------------------------
    # Change password
    # ---------------------------------------------

    def test_change_password_success(self):
        self.authenticate()
        data = {
            'old_password': 'StrongPass123!',
            'new_password': 'BrandNewPass456!',
            'new_password_confirm': 'BrandNewPass456!',
        }
        response = self.client.post('/api/users/change-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass456!'))

    def test_change_password_wrong_old_password(self):
        self.authenticate()
        data = {
            'old_password': 'WrongPassword123!',
            'new_password': 'BrandNewPass456!',
            'new_password_confirm': 'BrandNewPass456!',
        }
        response = self.client.post('/api/users/change-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('StrongPass123!'))

    def test_change_password_mismatched_confirm(self):
        self.authenticate()
        data = {
            'old_password': 'StrongPass123!',
            'new_password': 'BrandNewPass456!',
            'new_password_confirm': 'DifferentPass789!',
        }
        response = self.client.post('/api/users/change-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_same_as_old(self):
        self.authenticate()
        data = {
            'old_password': 'StrongPass123!',
            'new_password': 'StrongPass123!',
            'new_password_confirm': 'StrongPass123!',
        }
        response = self.client.post('/api/users/change-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_requires_authentication(self):
        data = {
            'old_password': 'StrongPass123!',
            'new_password': 'BrandNewPass456!',
            'new_password_confirm': 'BrandNewPass456!',
        }
        response = self.client.post('/api/users/change-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ---------------------------------------------
    # Account deactivation
    # ---------------------------------------------

    def test_deactivate_account(self):
        self.authenticate()
        response = self.client.post(
            '/api/users/deactivate/', {'password': 'StrongPass123!'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_deactivate_account_wrong_password(self):
        self.authenticate()
        response = self.client.post(
            '/api/users/deactivate/', {'password': 'WrongPassword123!'}, format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_delete_me_deactivates_account(self):
        self.authenticate()
        response = self.client.delete(self.url, {'password': 'StrongPass123!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
