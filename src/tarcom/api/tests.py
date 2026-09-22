from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from tarcom.base.models import CustomUser, OTPCode
from tarcom.utils.enums import CodeTypes


class SignupViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/signup/'

    def test_signup_creates_unverified_user(self):
        data = {
            'email': 'test@example.com',
            'password': 'StrongPass123!',
            'first_name': 'Test',
            'last_name': 'User',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = CustomUser.objects.get(email='test@example.com')
        self.assertFalse(user.is_verified)
        self.assertTrue(OTPCode.objects.filter(email='test@example.com', code_type=CodeTypes.SIGNUP).exists())

    def test_signup_duplicate_email(self):
        CustomUser.objects.create_user(email='test@example.com', password='StrongPass123!')
        data = {
            'email': 'test@example.com',
            'password': 'StrongPass123!',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/login/'
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='StrongPass123!', is_verified=True
        )

    def test_login_success(self):
        data = {'email': 'test@example.com', 'password': 'StrongPass123!'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('tokens', response.data)
        self.assertIn('user', response.data)

    def test_login_invalid_credentials(self):
        data = {'email': 'test@example.com', 'password': 'WrongPassword123!'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_unverified_user(self):
        user = CustomUser.objects.create_user(
            email='unverified@example.com', password='StrongPass123!', is_verified=False
        )
        data = {'email': 'unverified@example.com', 'password': 'StrongPass123!'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('needs_verification', response.data)


class VerifyOtpViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/verify-otp/'
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='StrongPass123!', is_verified=False
        )
        self.code = self.user.create_otp(code_type=CodeTypes.SIGNUP)

    def test_verify_otp_success(self):
        data = {'email': 'test@example.com', 'code': self.code, 'code_type': CodeTypes.SIGNUP}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)
        self.assertIn('tokens', response.data)

    def test_verify_otp_invalid_code(self):
        data = {'email': 'test@example.com', 'code': 000000, 'code_type': CodeTypes.SIGNUP}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginAfterVerificationTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/login/'
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='StrongPass123!', is_verified=True
        )

    def test_login_returns_tokens_and_user(self):
        data = {'email': 'test@example.com', 'password': 'StrongPass123!'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertEqual(response.data['user']['email'], 'test@example.com')


class OtpRateLimitTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/send-otp/'
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='StrongPass123!', is_verified=False
        )

    def test_rate_limit_enforced(self):
        for _ in range(5):
            OTPCode.objects.create(email='test@example.com', code_type=CodeTypes.SIGNUP)
        data = {'email': 'test@example.com', 'code_type': CodeTypes.SIGNUP}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ForgetPasswordViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/forget-password/'
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='StrongPass123!'
        )

    def test_forget_password_sends_otp(self):
        data = {'email': 'test@example.com'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            OTPCode.objects.filter(
                email='test@example.com', code_type=CodeTypes.RESET_PASSWORD
            ).exists()
        )

    def test_forget_password_nonexistent_email(self):
        data = {'email': 'nobody@example.com'}
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


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
