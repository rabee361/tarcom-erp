from django.core.signing import TimestampSigner
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response
from tarcom.base.models import *

# from tarcom.utils.emails import send_otp_email
from ..filters import *
from ..serializers import *

signer = TimestampSigner()


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


@extend_schema_view(
    list=extend_schema(tags=["Units of Measure"], summary="List units of measure"),
    retrieve=extend_schema(
        tags=["Units of Measure"], summary="Retrieve a unit of measure"
    ),
    create=extend_schema(
        tags=["Units of Measure"], summary="Create a unit of measure (admin only)"
    ),
    update=extend_schema(
        tags=["Units of Measure"], summary="Replace a unit of measure (admin only)"
    ),
    partial_update=extend_schema(
        tags=["Units of Measure"],
        summary="Partially update a unit of measure (admin only)",
    ),
    destroy=extend_schema(
        tags=["Units of Measure"], summary="Delete a unit of measure (admin only)"
    ),
)
class UnitOfMeasureViewSet(viewsets.ModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = UnitOfMeasureFilter


@extend_schema_view(
    list=extend_schema(tags=["Categories"], summary="List material categories"),
    retrieve=extend_schema(tags=["Categories"], summary="Retrieve a material category"),
    create=extend_schema(
        tags=["Categories"], summary="Create a material category (admin only)"
    ),
    update=extend_schema(
        tags=["Categories"], summary="Replace a material category (admin only)"
    ),
    partial_update=extend_schema(
        tags=["Categories"], summary="Partially update a material category (admin only)"
    ),
    destroy=extend_schema(
        tags=["Categories"], summary="Delete a material category (admin only)"
    ),
)
class MaterialCategoryViewSet(viewsets.ModelViewSet):
    queryset = MaterialCategory.objects.all()
    serializer_class = MaterialCategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MaterialCategoryFilter


@extend_schema_view(
    list=extend_schema(tags=["Materials"], summary="List materials"),
    retrieve=extend_schema(tags=["Materials"], summary="Retrieve a material"),
    create=extend_schema(tags=["Materials"], summary="Create a material"),
    update=extend_schema(tags=["Materials"], summary="Replace a material"),
    partial_update=extend_schema(
        tags=["Materials"], summary="Partially update a material"
    ),
    destroy=extend_schema(tags=["Materials"], summary="Delete a material"),
)
class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.select_related("category", "uom").all()
    serializer_class = MaterialSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MaterialFilter

    @extend_schema(
        tags=["Materials"],
        summary="List the companies used by materials",
        description=(
            "Plain array of distinct company names, sorted. Accepts the same "
            "filters as the list endpoint, so `?category=<id>` narrows it to the "
            "companies of that category's materials."
        ),
        responses={200: {"type": "array", "items": {"type": "string"}}},
    )
    @action(detail=False, methods=["get"])
    def companies(self, request):
        companies = (
            self.filter_queryset(self.get_queryset())
            .exclude(company="")
            .order_by("company")
            .values_list("company", flat=True)
            .distinct()
        )
        return Response(list(companies))


@extend_schema_view(
    list=extend_schema(tags=["Features"], summary="List featured materials"),
    retrieve=extend_schema(tags=["Features"], summary="Retrieve a featured material"),
)
class MaterialFeatureViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Material.objects.filter(is_feature=True).select_related("category", "uom")
    serializer_class = FeatureMaterialSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MaterialFilter


@extend_schema_view(
    list=extend_schema(tags=["Settings"], summary="List settings"),
    retrieve=extend_schema(tags=["Settings"], summary="Retrieve a setting"),
    create=extend_schema(tags=["Settings"], summary="Create a setting (admin only)"),
    update=extend_schema(tags=["Settings"], summary="Replace a setting (admin only)"),
    partial_update=extend_schema(
        tags=["Settings"], summary="Partially update a setting (admin only)"
    ),
    destroy=extend_schema(tags=["Settings"], summary="Delete a setting (admin only)"),
)
class SettingsViewSet(viewsets.ModelViewSet):
    queryset = Setting.objects.all()
    serializer_class = SettingSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = SettingFilter
