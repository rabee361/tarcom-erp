from rest_framework import status, viewsets, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, BasePermission, IsAdminUser, IsAuthenticated, SAFE_METHODS
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from django.core.signing import TimestampSigner
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from tarcom.base.models import CustomUser, OTPCode, UnitOfMeasure, MaterialCategory, Material
from tarcom.utils.enums import CodeTypes
# from tarcom.utils.helper import send_otp_email

from .serializers import *

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
            return Response(
                {"error": "Too many requests. Please try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
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
        tags=['Users'],
        request={'GET': None, 'PATCH': UserProfileUpdateSerializer},
        responses={200: UserSerializer, 401: ErrorResponseSerializer},
        summary="Get or update the current user's profile",
        description='Authenticated users can read and update their own profile '
                    '(first name, last name, phone, avatar).',
    )
    @action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated], url_path='me', url_name='me')
    def me(self, request):
        if request.method == 'PATCH':
            serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(UserSerializer(request.user).data)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


@extend_schema_view(
    list=extend_schema(tags=['Units of Measure'], summary='List units of measure'),
    retrieve=extend_schema(tags=['Units of Measure'], summary='Retrieve a unit of measure'),
    create=extend_schema(tags=['Units of Measure'], summary='Create a unit of measure (admin only)'),
    update=extend_schema(tags=['Units of Measure'], summary='Replace a unit of measure (admin only)'),
    partial_update=extend_schema(tags=['Units of Measure'], summary='Partially update a unit of measure (admin only)'),
    destroy=extend_schema(tags=['Units of Measure'], summary='Delete a unit of measure (admin only)'),
)
class UnitOfMeasureViewSet(viewsets.ModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'name_en', 'name_ar', 'code']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']


@extend_schema_view(
    list=extend_schema(
        tags=['Categories'],
        summary='List material categories',
        parameters=[
            OpenApiParameter(
                name='parent',
                type=str,
                required=False,
                description="Filter by parent category id, or one of `null`/`none`/`root` for top-level categories.",
            ),
        ],
    ),
    retrieve=extend_schema(tags=['Categories'], summary='Retrieve a material category'),
    create=extend_schema(tags=['Categories'], summary='Create a material category (admin only)'),
    update=extend_schema(tags=['Categories'], summary='Replace a material category (admin only)'),
    partial_update=extend_schema(tags=['Categories'], summary='Partially update a material category (admin only)'),
    destroy=extend_schema(tags=['Categories'], summary='Delete a material category (admin only)'),
)
class MaterialCategoryViewSet(viewsets.ModelViewSet):
    queryset = MaterialCategory.objects.all()
    serializer_class = MaterialCategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'name_en', 'name_ar']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset()
        parent_id = self.request.query_params.get('parent')
        if parent_id is not None:
            if parent_id.lower() in ['null', 'none', 'root']:
                qs = qs.filter(parent__isnull=True)
            else:
                qs = qs.filter(parent_id=parent_id)
        return qs

    @extend_schema(
        tags=['Categories'],
        summary='Get the category tree',
        description='Returns root categories with nested subcategories.',
    )
    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Returns root categories with nested subcategories."""
        roots = self.get_queryset().filter(parent__isnull=True)
        serializer = self.get_serializer(roots, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=['Materials (Products)'],
        summary='List materials (products)',
        parameters=[
            OpenApiParameter(name='category', type=int, required=False,
                             description='Filter by category id.'),
            OpenApiParameter(name='is_active', type=bool, required=False,
                             description='Filter by active flag (true/false).'),
        ],
    ),
    retrieve=extend_schema(tags=['Materials (Products)'], summary='Retrieve a material (product)'),
    create=extend_schema(tags=['Materials (Products)'], summary='Create a material (product)'),
    update=extend_schema(tags=['Materials (Products)'], summary='Replace a material (product)'),
    partial_update=extend_schema(tags=['Materials (Products)'], summary='Partially update a material (product)'),
    destroy=extend_schema(tags=['Materials (Products)'], summary='Delete a material (product)'),
)
class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.select_related('category', 'uom').all()
    serializer_class = MaterialSerializer
    # permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'name_en', 'name_ar']
    ordering_fields = ['consumer_price', 'supplier_price', 'created_at', 'name']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        category_id = self.request.query_params.get('category')
        if category_id:
            qs = qs.filter(category_id=category_id)
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ['true', '1'])
        return qs

