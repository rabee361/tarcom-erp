from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.core.signing import TimestampSigner

from tarcom.base.models import CustomUser, OTPCode
from tarcom.utils.enums import CodeTypes
from tarcom.utils.helper import send_otp_email

from .serializers import (
    UserSerializer,
    SignupSerializer,
    LoginSerializer,
    SendOtpSerializer,
    VerifyOtpSerializer,
    ForgetPasswordSerializer,
    ResetPasswordSerializer,
)

signer = TimestampSigner()


class SignupView(APIView):
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        code = user.create_otp(code_type=CodeTypes.SIGNUP)
        send_otp_email(user.email, code, CodeTypes.SIGNUP)
        return Response(
            {"message": "Account created. Please verify your email.", "email": user.email},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            "tokens": {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            "user": UserSerializer(user).data,
        })


class SendOtpView(APIView):
    def post(self, request):
        serializer = SendOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        code_type = serializer.validated_data['code_type']
        user = CustomUser.objects.get(email=email)
        code = user.create_otp(code_type=code_type)
        send_otp_email(email, code, code_type)
        return Response({"message": "OTP code sent successfully."})


class VerifyOtpView(APIView):
    def post(self, request):
        serializer = VerifyOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data['otp']
        otp.is_used = True
        otp.save()

        if otp.code_type == CodeTypes.SIGNUP:
            user = CustomUser.objects.get(email=otp.email)
            user.is_verified = True
            user.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                "message": "Account verified successfully.",
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
                "user": UserSerializer(user).data,
            })
        else:
            reset_token = signer.sign(otp.email)
            return Response({
                "message": "OTP verified. Use the reset token to reset your password.",
                "reset_token": reset_token,
            })


class ForgetPasswordView(APIView):
    def post(self, request):
        serializer = ForgetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = CustomUser.objects.get(email=email)
        if OTPCode.check_limit(email):
            return Response(
                {"error": "Too many requests. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        code = user.create_otp(code_type=CodeTypes.RESET_PASSWORD)
        send_otp_email(email, code, CodeTypes.RESET_PASSWORD)
        return Response({"message": "Password reset OTP sent to your email."})


class ResetPasswordView(APIView):
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        new_password = serializer.validated_data['new_password']
        user = CustomUser.objects.get(email=email)

        if serializer.validated_data.get('reset_token'):
            try:
                verified_email = signer.unsign(serializer.validated_data['reset_token'], max_age=600)
                if verified_email != email:
                    return Response(
                        {"error": "Token does not match email."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception:
                return Response(
                    {"error": "Invalid or expired reset token."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            code = serializer.validated_data['code']
            otp = OTPCode.objects.filter(
                email=email, code=code,
                code_type__in=[CodeTypes.RESET_PASSWORD, CodeTypes.FORGET_PASSWORD],
                is_used=False,
            ).first()
            if not otp:
                return Response(
                    {"error": "Invalid or already used OTP code."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if otp.is_expired:
                return Response(
                    {"error": "OTP code has expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            otp.is_used = True
            otp.save()

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password reset successfully. You can now log in."})
