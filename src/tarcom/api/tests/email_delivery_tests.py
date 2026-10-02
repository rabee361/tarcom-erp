from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import CustomUser, OTPCode
from tarcom.utils.emails import send_otp_email
from tarcom.utils.enums import CodeTypes


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SendOtpEmailTest(TestCase):
    def test_returns_true_when_backend_accepts(self):
        self.assertIs(send_otp_email('a@b.com', 123456, CodeTypes.SIGNUP), True)
        self.assertEqual(len(mail.outbox), 1)

    def test_returns_false_instead_of_raising_on_transport_error(self):
        with patch('tarcom.utils.emails.send_mail', side_effect=OSError('smtp down')):
            self.assertIs(send_otp_email('a@b.com', 123456, CodeTypes.SIGNUP), False)

    def test_signup_copy_for_verification(self):
        send_otp_email('a@b.com', 123456, CodeTypes.SIGNUP)
        body = mail.outbox[0].body
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('Verification Code', mail.outbox[0].subject)
        self.assertIn('123456', body)
        self.assertIn('verify your account', html)
        self.assertNotIn('Password Reset', html)

    def test_password_reset_copy_does_not_claim_account_verification(self):
        for code_type in (CodeTypes.RESET_PASSWORD, CodeTypes.FORGET_PASSWORD):
            mail.outbox.clear()
            send_otp_email('a@b.com', 123456, code_type)
            html = mail.outbox[0].alternatives[0][0]
            self.assertIn('Password Reset Code', mail.outbox[0].subject)
            self.assertIn('reset the password', html)
            self.assertNotIn('verify your account', html)

    def test_expiry_minutes_come_from_the_model_setting(self):
        send_otp_email('a@b.com', 123456, CodeTypes.SIGNUP)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('expire in 10 minutes', mail.outbox[0].body)
        self.assertIn('expire in 10 minutes', html)

    def test_recipient_name_is_used_when_known(self):
        send_otp_email('a@b.com', 123456, CodeTypes.SIGNUP, recipient_name='Rabi')
        self.assertIn('Hello Rabi,', mail.outbox[0].alternatives[0][0])

    def test_falls_back_to_generic_greeting_without_a_name(self):
        send_otp_email('a@b.com', 123456, CodeTypes.SIGNUP)
        self.assertIn('Hello There!', mail.outbox[0].alternatives[0][0])


class SignupMailFailureTest(TestCase):
    """A transport failure must not strand an account or 500 the request."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.url = '/api/auth/signup/'

    def test_signup_survives_mail_failure_and_reports_it(self):
        with patch('tarcom.utils.emails.send_mail', side_effect=OSError('smtp down')):
            response = self.client.post(
                self.url,
                {'email': 'test@example.com', 'password': 'StrongPass123!'},
                format='json',
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data['email_sent'])
        self.assertIn('send-otp', response.data['message'])

    def test_account_and_otp_persist_so_the_code_can_be_re_requested(self):
        with patch('tarcom.utils.emails.send_mail', side_effect=OSError('smtp down')):
            self.client.post(
                self.url,
                {'email': 'test@example.com', 'password': 'StrongPass123!'},
                format='json',
            )

        self.assertTrue(CustomUser.objects.filter(email='test@example.com').exists())
        self.assertTrue(
            OTPCode.objects.filter(
                email='test@example.com', code_type=CodeTypes.SIGNUP, is_used=False
            ).exists()
        )

    def test_signup_reports_success_when_mail_is_accepted(self):
        response = self.client.post(
            self.url,
            {'email': 'test@example.com', 'password': 'StrongPass123!'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['email_sent'])


class AuthThrottleTest(TestCase):
    """signup and send-otp are anonymous and each can trigger an outbound mail."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_anonymous_signup_is_rate_limited(self):
        codes = []
        for index in range(31):
            response = self.client.post(
                '/api/auth/signup/',
                {'email': f'user{index}@example.com', 'password': 'StrongPass123!'},
                format='json',
            )
            codes.append(response.status_code)

        self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, codes)
        self.assertEqual(codes[0], status.HTTP_201_CREATED)
