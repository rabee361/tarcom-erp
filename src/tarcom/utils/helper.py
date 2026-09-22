import random
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings


def generate_code():
    return random.randint(100000, 999999)


def get_expiration_time():
    from datetime import timedelta
    return timezone.now() + timedelta(minutes=10)


def send_otp_email(email, code, code_type):
    subject = 'Your Verification Code'
    if code_type == 'RESET_PASSWORD' or code_type == 'FORGET_PASSWORD':
        subject = 'Your Password Reset Code'
    message = f'Your verification code is: {code}\nThis code will expire in 10 minutes.'
    send_mail(
        subject,
        message,
        getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@tarcom.com'),
        [email],
        fail_silently=False,
    )
