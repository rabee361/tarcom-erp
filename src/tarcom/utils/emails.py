import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from tarcom.utils.enums import CodeTypes
from tarcom.utils.helper import OTP_EXPIRY_MINUTES

logger = logging.getLogger(__name__)

PASSWORD_RESET_TYPES = {CodeTypes.RESET_PASSWORD, CodeTypes.FORGET_PASSWORD}


def send_otp_email(email, code, code_type, recipient_name=''):
    """
    Deliver an OTP code by email.

    Returns True only when the mail backend accepted the message. Never raises:
    a transport failure must not strand an account whose row is already
    committed, so the caller decides what to tell the client. Gmail accepts
    unknown recipients at RCPT time, so True means "handed to the provider",
    not "delivered" -- bounce handling is a separate concern.
    """
    is_password_reset = code_type in PASSWORD_RESET_TYPES

    if is_password_reset:
        subject = _("Your Password Reset Code")
        message = (
            f'Your password reset code is: {code}\n'
            f'This code will expire in {OTP_EXPIRY_MINUTES} minutes.'
        )
    else:
        subject = _("Your Verification Code")
        message = (
            f'Your verification code is: {code}\n'
            f'This code will expire in {OTP_EXPIRY_MINUTES} minutes.'
        )

    try:
        return bool(send_mail(
            subject,
            message,
            getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@tarcom.com'),
            [email],
            fail_silently=False,
            html_message=render_to_string('email/email_code.html', {
                'code': code,
                'code_type': code_type,
                'is_password_reset': is_password_reset,
                'expiry_minutes': OTP_EXPIRY_MINUTES,
                'recipient_name': recipient_name,
            })
        ))
    except Exception:
        logger.exception('OTP email delivery failed for %s (code_type=%s)', email, code_type)
        return False