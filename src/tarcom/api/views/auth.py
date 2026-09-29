from rest_framework import status, viewsets, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAdminUser, IsAuthenticated, SAFE_METHODS
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from django.core.signing import TimestampSigner
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from tarcom.base.models import CustomUser, OTPCode, UnitOfMeasure, MaterialCategory, Material
from tarcom.utils.enums import CodeTypes
# from tarcom.utils.helper import send_otp_email

from ..serializers import *

signer = TimestampSigner()



class AuthViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        # Mirrors rest_framework_simplejwt.views.TokenViewBase: a WWW-Authenticate
        # header must be available so token errors (InvalidToken, an
        # AuthenticationFailed subclass) keep their 401 status instead of being
        # downgraded to 403 by DRF when authentication classes are empty.
        return '{} realm="api"'.format(jwt_settings.AUTH_HEADER_TYPES[0])

    @extend_schema(
        tags=['Auth'],
        request=SignupSerializer,
        responses={201: SignupResponseSerializer, 400: ErrorResponseSerializer},
        summary='Create a new account',
        description='Creates an unverified user and generates a SIGNUP OTP code.',
    )
    @action(detail=False, methods=['post'], url_path='signup', url_name='signup')
    def signup(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        code = user.create_otp(code_type=CodeTypes.SIGNUP)
        # send_otp_email(user.email, code, CodeTypes.SIGNUP)
        return Response(
            {"message": "Account created. Please verify your email.", "email": user.email},
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=['Auth'],
        request=LoginSerializer,
        responses={200: TokenResponseSerializer, 400: ErrorResponseSerializer},
        summary='Log in with email and password',
        description='Returns JWT tokens and the user profile for a verified, active account.',
    )
    @action(detail=False, methods=['post'], url_path='login', url_name='login')
    def login(self, request):
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

    @extend_schema(
        tags=['Auth'],
        request=TokenRefreshSerializer,
        responses={200: TokenRefreshResponseSerializer, 400: ErrorResponseSerializer,
                   401: ErrorResponseSerializer},
        summary='Refresh the access token',
        description='POST a `refresh` token to obtain a new `access` token.',
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='token/refresh',
        url_name='token-refresh',
        authentication_classes=[],
    )
    def token_refresh(self, request):
        # Mirrors rest_framework_simplejwt.views.TokenRefreshView behavior:
        # TokenError (invalid/expired refresh token) must surface as HTTP 400.
        serializer = TokenRefreshSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        return Response(serializer.validated_data)

    @extend_schema(
        tags=['OTP & Password'],
        request=SendOtpSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer, 429: ErrorResponseSerializer},
        summary='Send an OTP code by email (backward-compatible alias)',
    )
    @action(detail=False, methods=['post'], url_path='send-otp', url_name='send-otp')
    def send_otp(self, request):
        return OTPViewSet().send_otp(request)

    @extend_schema(
        tags=['OTP & Password'],
        request=VerifyOtpSerializer,
        responses={200: VerifyOtpResponseSerializer, 400: ErrorResponseSerializer},
        summary='Verify an OTP code (backward-compatible alias)',
    )
    @action(detail=False, methods=['post'], url_path='verify-otp', url_name='verify-otp')
    def verify_otp(self, request):
        return OTPViewSet().verify_otp(request)

    @extend_schema(
        tags=['OTP & Password'],
        request=ForgetPasswordSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer, 429: ErrorResponseSerializer},
        summary='Start password recovery (backward-compatible alias)',
    )
    @action(detail=False, methods=['post'], url_path='forget-password', url_name='forget-password')
    def forget_password(self, request):
        return OTPViewSet().forget_password(request)

    @extend_schema(
        tags=['OTP & Password'],
        request=ResetPasswordSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer},
        summary='Reset the account password (backward-compatible alias)',
    )
    @action(detail=False, methods=['post'], url_path='reset-password', url_name='reset-password')
    def reset_password(self, request):
        return OTPViewSet().reset_password(request)


class OTPViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['OTP & Password'],
        request=SendOtpSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer, 429: ErrorResponseSerializer},
        summary='Send an OTP code by email',
        description='Rate limited: at most 5 codes per email within 15 minutes.',
    )
    @action(detail=False, methods=['post'], url_path='send-otp', url_name='send-otp')
    def send_otp(self, request):
        serializer = SendOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        code_type = serializer.validated_data['code_type']
        user = CustomUser.objects.get(email=email)
        code = user.create_otp(code_type=code_type)
        # send_otp_email(email, code, code_type)
        return Response({"message": "OTP code sent successfully."})

    @extend_schema(
        tags=['OTP & Password'],
        request=VerifyOtpSerializer,
        responses={200: VerifyOtpResponseSerializer, 400: ErrorResponseSerializer},
        summary='Verify an OTP code',
        description=(
            'SIGNUP: marks the account verified and returns JWT tokens. '
            'Password flows: returns a signed `reset_token` valid for 10 minutes.'
        ),
    )
    @action(detail=False, methods=['post'], url_path='verify-otp', url_name='verify-otp')
    def verify_otp(self, request):
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

    @extend_schema(
        tags=['OTP & Password'],
        request=ForgetPasswordSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer, 429: ErrorResponseSerializer},
        summary='Start password recovery',
        description='Generates a RESET_PASSWORD OTP for the given email.',
    )
    @action(detail=False, methods=['post'], url_path='forget-password', url_name='forget-password')
    def forget_password(self, request):
        serializer = ForgetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = CustomUser.objects.get(email=email)
        if OTPCode.check_limit(email):
            raise Throttled(detail="Too many requests. Please try again later.")
        code = user.create_otp(code_type=CodeTypes.RESET_PASSWORD)
        # send_otp_email(email, code, CodeTypes.RESET_PASSWORD)
        return Response({"message": "Password reset OTP sent to your email."})

    @extend_schema(
        tags=['OTP & Password'],
        request=ResetPasswordSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer},
        summary='Reset the account password',
        description='Accepts either a `code` (OTP) or a `reset_token` issued by verify-otp.',
    )
    @action(detail=False, methods=['post'], url_path='reset-password', url_name='reset-password')
    def reset_password(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        new_password = serializer.validated_data['new_password']
        user = CustomUser.objects.get(email=email)

        if serializer.validated_data.get('reset_token'):
            try:
                verified_email = signer.unsign(serializer.validated_data['reset_token'], max_age=600)
            except Exception:
                raise ValidationError({"non_field_errors": ["Invalid or expired reset token."]})
            if verified_email != email:
                raise ValidationError({"non_field_errors": ["Token does not match email."]})
        else:
            code = serializer.validated_data['code']
            otp = OTPCode.objects.filter(
                email=email, code=code,
                code_type__in=[CodeTypes.RESET_PASSWORD, CodeTypes.FORGET_PASSWORD],
                is_used=False,
            ).first()
            if not otp:
                raise ValidationError({"non_field_errors": ["Invalid or already used OTP code."]})
            if otp.is_expired:
                raise ValidationError({"non_field_errors": ["OTP code has expired."]})
            otp.is_used = True
            otp.save()

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password reset successfully. You can now log in."})


@extend_schema_view(
    list=extend_schema(tags=['Users'], summary='List all users (admin only)'),
    retrieve=extend_schema(tags=['Users'], summary='Retrieve a user (admin only)'),
    create=extend_schema(tags=['Users'], summary='Create a user (admin only)'),
    update=extend_schema(tags=['Users'], summary='Replace a user (admin only)'),
    partial_update=extend_schema(tags=['Users'], summary='Partially update a user (admin only)'),
    destroy=extend_schema(tags=['Users'], summary='Delete a user (admin only)'),
)
class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=['Profile'],
        request={'GET': None, 'PUT': UserProfileUpdateSerializer, 'PATCH': UserProfileUpdateSerializer,
                 'DELETE': AccountDeactivateSerializer},
        responses={200: UserSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer},
        summary="Get or update the current user's profile",
        description='Authenticated users can view and update their profile (first name, last name, phone, avatar). '
                    'DELETE deactivates the account after password confirmation.',
    )
    @action(detail=False, methods=['get', 'put', 'patch', 'delete'], permission_classes=[IsAuthenticated],
            url_path='me', url_name='me')
    def me(self, request):
        if request.method in ['PUT', 'PATCH']:
            partial = (request.method == 'PATCH')
            serializer = UserProfileUpdateSerializer(
                request.user, data=request.data, partial=partial, context={'request': request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
        elif request.method == 'DELETE':
            serializer = AccountDeactivateSerializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            user = request.user
            user.is_active = False
            user.save(update_fields=['is_active'])
            return Response({"message": _("Account deactivated successfully.")}, status=status.HTTP_200_OK)
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        tags=['Profile'],
        request=None,
        responses={200: MessageResponseSerializer, 401: ErrorResponseSerializer},
        summary="Remove current user's avatar",
    )
    @action(detail=False, methods=['delete'], permission_classes=[IsAuthenticated],
            url_path='me/avatar', url_name='me-avatar')
    def remove_avatar(self, request):
        user = request.user
        if user.avatar:
            user.avatar.delete(save=False)
            user.avatar = None
            user.save(update_fields=['avatar'])
        return Response({"message": _("Avatar removed successfully.")}, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Profile'],
        request=ChangePasswordSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer},
        summary="Change current user's password",
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated],
            url_path='change-password', url_name='change-password')
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": _("Password changed successfully.")}, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Profile'],
        request=AccountDeactivateSerializer,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer, 401: ErrorResponseSerializer},
        summary="Deactivate account",
    )
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated],
            url_path='deactivate', url_name='deactivate')
    def deactivate(self, request):
        serializer = AccountDeactivateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({"message": _("Account deactivated successfully.")}, status=status.HTTP_200_OK)
