from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from tarcom.base.models import CustomUser, OTPCode, UnitOfMeasure, MaterialCategory, Material
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



# ==========================================
# AuthViewSet
# ==========================================
# Note: signup/login are covered by SignupViewTest/LoginViewTest above,
# which now hit AuthViewSet's router actions.

class AuthViewSetTokenRefreshTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='StrongPass123!', is_verified=True
        )

    def test_token_refresh_returns_new_access_token(self):
        login = self.client.post(
            '/api/auth/login/',
            {'email': 'test@example.com', 'password': 'StrongPass123!'},
            format='json',
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

        response = self.client.post(
            '/api/auth/token/refresh/',
            {'refresh': login.data['tokens']['refresh']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_token_refresh_invalid_token(self):
        # Matches rest_framework_simplejwt's TokenRefreshView behavior:
        # an invalid refresh token yields 401 with a "detail" payload.
        response = self.client.post(
            '/api/auth/token/refresh/',
            {'refresh': 'not-a-valid-token'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)




# ==========================================
# OTPViewSet (canonical /api/otp/ routes)
# ==========================================

class OTPViewSetRoutingTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='test@example.com', password='StrongPass123!', is_verified=False
        )
        self.signup_code = self.user.create_otp(code_type=CodeTypes.SIGNUP)

    def test_send_otp_canonical_route(self):
        data = {'email': 'test@example.com', 'code_type': CodeTypes.SIGNUP}
        response = self.client.post('/api/otp/send-otp/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)

    def test_send_otp_backward_compatible_alias(self):
        data = {'email': 'test@example.com', 'code_type': CodeTypes.SIGNUP}
        response = self.client.post('/api/auth/send-otp/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)

    def test_verify_otp_canonical_route(self):
        data = {'email': 'test@example.com', 'code': self.signup_code, 'code_type': CodeTypes.SIGNUP}
        response = self.client.post('/api/otp/verify-otp/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified)
        self.assertIn('tokens', response.data)

    def test_forget_password_canonical_route(self):
        response = self.client.post('/api/otp/forget-password/', {'email': 'test@example.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            OTPCode.objects.filter(email='test@example.com', code_type=CodeTypes.RESET_PASSWORD).exists()
        )

    def test_reset_password_canonical_route(self):
        reset_code = self.user.create_otp(code_type=CodeTypes.RESET_PASSWORD)
        data = {
            'email': 'test@example.com',
            'code': reset_code,
            'new_password': 'NewStrongPass123!',
            'new_password_confirm': 'NewStrongPass123!',
        }
        response = self.client.post('/api/otp/reset-password/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass123!'))


# ==========================================
# UserViewSet (/me/ + admin permissions)
# ==========================================

class UserViewSetMeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            email='user@example.com',
            password='StrongPass123!',
            first_name='Old',
            last_name='Name',
            is_verified=True,
        )

    def test_me_requires_authentication(self):
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'user@example.com')

    def test_me_patch_updates_profile(self):
        self.client.force_authenticate(user=self.user)
        data = {'first_name': 'New', 'last_name': 'Person'}
        response = self.client.patch('/api/users/me/', data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], 'New')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')

    def test_me_patch_ignores_read_only_fields(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch('/api/users/me/', {'user_type': 'admin'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.user_type, 'buyer')


class UserViewSetAdminPermissionsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = CustomUser.objects.create_superuser(
            email='admin@tarcom.com', password='AdminPass123!'
        )
        self.buyer = CustomUser.objects.create_user(
            email='buyer@example.com', password='StrongPass123!', is_verified=True
        )

    def test_list_users_requires_admin(self):
        anon = self.client.get('/api/users/')
        self.assertEqual(anon.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.buyer)
        forbidden = self.client.get('/api/users/')
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        allowed = self.client.get('/api/users/')
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)

    def test_retrieve_user_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/users/{self.buyer.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'buyer@example.com')

