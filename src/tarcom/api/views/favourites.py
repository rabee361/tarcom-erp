from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

from tarcom.base.models import FavouriteItem, Material
from ..serializers import (
    FavouriteItemSerializer,
    FavouriteCreateSerializer,
    FavouriteToggleResponseSerializer,
    MessageResponseSerializer,
    ErrorResponseSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=['Favourites'], summary='List user favourites'),
    retrieve=extend_schema(tags=['Favourites'], summary='Retrieve favourite item details'),
    create=extend_schema(tags=['Favourites'], summary='Add material to favourites'),
    destroy=extend_schema(tags=['Favourites'], summary='Remove item from favourites by favourite ID'),
)
class FavouriteViewSet(viewsets.ModelViewSet):
    queryset = FavouriteItem.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        return FavouriteItem.objects.filter(user=self.request.user).select_related(
            'material', 'material__category', 'material__uom'
        )

    def get_serializer_class(self):
        if self.action == 'create':
            return FavouriteCreateSerializer
        return FavouriteItemSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        output_serializer = FavouriteItemSerializer(instance, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=['Favourites'],
        request=FavouriteCreateSerializer,
        responses={200: FavouriteToggleResponseSerializer, 400: ErrorResponseSerializer},
        summary='Toggle favourite status for a material',
        description='If the material is already in favourites, it is removed; otherwise, it is added.',
    )
    @action(detail=False, methods=['post'], url_path='toggle', url_name='toggle')
    def toggle(self, request):
        material_id = request.data.get('material')
        if not material_id:
            return Response({"error": "material field is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            material = Material.objects.get(id=material_id, is_active=True)
        except (Material.DoesNotExist, ValueError, TypeError):
            return Response({"error": "Active material not found."}, status=status.HTTP_404_NOT_FOUND)

        favourite = FavouriteItem.objects.filter(user=request.user, material=material).first()
        if favourite:
            favourite.delete()
            return Response({
                "is_favourite": False,
                "message": "Removed from favourites."
            }, status=status.HTTP_200_OK)
        else:
            FavouriteItem.objects.create(user=request.user, material=material)
            return Response({
                "is_favourite": True,
                "message": "Added to favourites."
            }, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Favourites'],
        parameters=[
            OpenApiParameter(name='material', type=int, required=True, description='Material ID to check')
        ],
        responses={200: FavouriteToggleResponseSerializer},
        summary='Check if material is in favourites',
    )
    @action(detail=False, methods=['get'], url_path='check', url_name='check')
    def check(self, request):
        material_id = request.query_params.get('material')
        if not material_id:
            return Response({"error": "material parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        is_fav = FavouriteItem.objects.filter(user=request.user, material_id=material_id).exists()
        return Response({"is_favourite": is_fav, "message": "Checked successfully."})

    @extend_schema(
        tags=['Favourites'],
        responses={200: MessageResponseSerializer, 404: ErrorResponseSerializer},
        summary='Remove material from favourites by material ID',
    )
    @action(detail=False, methods=['delete'], url_path='remove-by-material/(?P<material_id>[^/.]+)',
            url_name='remove-by-material')
    def remove_by_material(self, request, material_id=None):
        deleted_count, _ = FavouriteItem.objects.filter(user=request.user, material_id=material_id).delete()
        if deleted_count == 0:
            return Response({"error": "Material is not in favourites."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"message": "Material removed from favourites."}, status=status.HTTP_200_OK)
