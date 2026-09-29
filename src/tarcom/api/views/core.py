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

from ..serializers import *

signer = TimestampSigner()



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
    permission_classes = [IsAdminOrReadOnly]
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


@extend_schema_view(
    retrieve=extend_schema(tags=['Settings']),
    create=extend_schema(tags=['Settings'])
)
class SettingsViewSet(viewsets.ModelViewSet):
    queryset = Setting.objects.all()
    serializer_class = SettingSerializer
    search_fields = ['key', 'key_en', 'key_ar']
    ordering_fields = ['key']
