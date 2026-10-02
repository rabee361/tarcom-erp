import random
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings


OTP_EXPIRY_MINUTES = 10

def generate_code():
    return random.randint(100000, 999999)

def get_expiration_time():
    from datetime import timedelta
    return timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')
