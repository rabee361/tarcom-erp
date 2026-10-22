from decimal import Decimal, InvalidOperation
import secrets

from django.utils import timezone

OTP_CODE_DIGITS = 6
OTP_CODE_MIN = 100000
OTP_CODE_MAX = 999999
OTP_EXPIRY_MINUTES = 10


def generate_code():
    # `random` is a Mersenne Twister and predictable from observed output; this
    # value is emailed as an account-takeover credential, so use the OS CSPRNG.
    return secrets.randbelow(OTP_CODE_MAX - OTP_CODE_MIN + 1) + OTP_CODE_MIN


def get_expiration_time():
    from datetime import timedelta

    return timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")

def conversion_price():
    from tarcom.base.models import Setting

    try:
        return Decimal(Setting.objects.get(key_en="conversion_price").value)
    except (Setting.DoesNotExist, InvalidOperation):
        return Decimal("140")


def price_in_sp(price):
    if price is None:
        return None
    conversion = conversion_price()
    return str((price * conversion).quantize(Decimal("0.01")))
    