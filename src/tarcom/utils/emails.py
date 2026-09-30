import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string

from tarcom.base.models import Setting

def send_otp_email(otp_code, email):
    webhook_url = "http://localhost:5678/webhook/701d2178-946b-4638-ba13-7ee17fce2c4e"
    
    subject = 'رمز التحقق من بريدك الإلكتروني'
    html_message = render_to_string('emails/email_code.html', {
        'otp_code': otp_code
    })
    
    payload = {
        "email": email,
        "subject": subject,
        "body": html_message
    }
    
    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error sending email via n8n: {e}")
