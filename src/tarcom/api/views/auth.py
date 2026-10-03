from django.core.signing import TimestampSigner
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import Throttled
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import (
    AllowAny,
    IsAdminUser,
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken
from tarcom.base.models import CustomUser, OTPCode
from tarcom.utils.emails import send_otp_email
from tarcom.utils.enums import CodeTypes

from ..serializers import *

ValidationError = DRFValidationError

signer = TimestampSigner()


def _otp_delivery_response(email_sent, success_message=None, failure_message=None):
    """
    Report whether the OTP actually reached the mail provider.

    A 200 here means accepted for delivery, not delivered -- Gmail takes the
    address at face value and bounces unknown recipients later, so the client
    must still handle "code never arrived".
    """
    if email_sent:
        message = success_message or _("OTP code sent successfully.")
    else:
        message = failure_message or _(
            "We could not send the OTP code. Please try again in a few minutes."
        )
    return Response({"message": message, "email_sent": email_sent})



class AuthViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]
    # Strict tier: overrides the default browsing budget because every accepted
    # call here can trigger an outbound email. Keyed by user id when
    # authenticated, else by IP.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'otp'

    def get_authenticate_header(self, request):
        # Mirrors rest_framework_simplejwt.views.TokenViewBase: a WWW-Authenticate
        # header must be available so token errors (InvalidToken, an
        # AuthenticationFailed subclass) keep their 401 status instead of being
        # downgraded to 403 by DRF when authentication classes are empty.
        return f'{jwt_settings.AUTH_HEADER_TYPES[0]} realm="api"'

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

        # The user row and its OTP are either both persisted or neither is.
        # The network send stays outside the block: holding a transaction open
        # across SMTP would pin a database connection for the socket timeout.
        with transaction.atomic():
            user = serializer.save()
            code = user.create_otp(code_type=CodeTypes.SIGNUP)

        email_sent = send_otp_email(
            user.email, code, CodeTypes.SIGNUP, recipient_name=user.first_name
        )

        if email_sent:
            message = _("Account created. Please verify your email.")
        else:
            message = _(
                "Account created, but the verification code could not be emailed. "
                "Request a new code with the send-otp endpoint."
            )

        return Response(
            {"message": message, "email": user.email, "email_sent": email_sent},
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
        tags=['Auth'],
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
        with transaction.atomic():
            code = user.create_otp(code_type=code_type)
        return _otp_delivery_response(
            send_otp_email(email, code, code_type, recipient_name=user.first_name)
        )
    

    @extend_schema(
        tags=['Auth'],
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
                "message": _("Account verified successfully."),
                "tokens": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                },
                "user": UserSerializer(user).data,
            })
        else:
            reset_token = signer.sign(otp.email)
            return Response({
                "message": _("OTP verified. Use the reset token to reset your password."),
                "reset_token": reset_token,
            })

    @extend_schema(
        tags=['Auth'],
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
            raise Throttled(detail=_("Too many requests. Please try again later."))
        with transaction.atomic():
            code = user.create_otp(code_type=CodeTypes.RESET_PASSWORD)
        return _otp_delivery_response(
            send_otp_email(email, code, CodeTypes.RESET_PASSWORD, recipient_name=user.first_name),
            success_message=_("Password reset OTP sent to your email."),
            failure_message=_(
                "We could not email the password reset code. Please try again later."
            ),
        )

    @extend_schema(
        tags=['Auth'],
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
                raise ValidationError({"non_field_errors": [_("Invalid or expired reset token.")]})
            if verified_email != email:
                raise ValidationError({"non_field_errors": [_("Token does not match email.")]})
        else:
            code = serializer.validated_data['code']
            otp = OTPCode.objects.filter(
                email=email, code=code,
                code_type__in=[CodeTypes.RESET_PASSWORD, CodeTypes.FORGET_PASSWORD],
                is_used=False,
            ).first()
            if not otp:
                raise ValidationError({"non_field_errors": [_("Invalid or already used OTP code.")]})
            if otp.is_expired:
                raise ValidationError({"non_field_errors": [_("OTP code has expired.")]})
            otp.is_used = True
            otp.save()

        user.set_password(new_password)
        user.save()
        return Response({"message": _("Password reset successfully. You can now log in.")})


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
