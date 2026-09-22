from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    SignupView,
    LoginView,
    SendOtpView,
    VerifyOtpView,
    ForgetPasswordView,
    ResetPasswordView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='auth_signup'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('send-otp/', SendOtpView.as_view(), name='auth_send_otp'),
    path('verify-otp/', VerifyOtpView.as_view(), name='auth_verify_otp'),
    path('forget-password/', ForgetPasswordView.as_view(), name='auth_forget_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='auth_reset_password'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
