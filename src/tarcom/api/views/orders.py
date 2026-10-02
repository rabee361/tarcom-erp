from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from tarcom.base.models import Order, OrderStatus

from ..filters import OrderFilter
from ..serializers import *

# Re-bound after the star import above, which re-exports
# django.core.exceptions.ValidationError and would otherwise
# turn these raises into 500s instead of DRF 400s.


@extend_schema_view(
    list=extend_schema(
        tags=['Orders'],
        summary='List orders',
        description='Customers see only their own orders. Staff and admins see all orders across the system.',
    ),
    retrieve=extend_schema(tags=['Orders'], summary='Retrieve order details with items'),
    create=extend_schema(tags=['Orders'], summary='Create/place an order (Checkout)'),
    partial_update=extend_schema(
        tags=['Orders'],
        summary='Partially update an order',
        description='http_method_names restricts this viewset to GET/POST/PATCH, so PUT and DELETE are not routed.',
    ),
)
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderFilter
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or getattr(user, 'is_admin', False):
            queryset = Order.objects.all()
        else:
            queryset = Order.objects.filter(user=user)
        return queryset.select_related('user').prefetch_related('items__material', 'items__material__uom')

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        elif self.action == 'list':
            return OrderListSerializer
        elif self.action == 'update_status':
            return OrderStatusUpdateSerializer
        return OrderDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        output_serializer = OrderDetailSerializer(order, context={'request': request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=['Orders'],
        request=None,
        responses={200: MessageResponseSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer},
        summary='Cancel an order',
        description='Customers can cancel their own order only while status is PENDING. Admins can cancel anytime prior to delivery.',
    )
    @action(detail=True, methods=['post'], url_path='cancel', url_name='cancel')
    def cancel(self, request, pk=None):
        order = self.get_object()
        user = request.user

        if not (user.is_staff or getattr(user, 'is_admin', False)):
            if order.status != OrderStatus.PENDING:
                raise ValidationError({"non_field_errors": [
                    _("Orders can only be cancelled while in PENDING status.")
                ]})

        if order.status in [OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
            raise ValidationError({"non_field_errors": [
                _("Cannot cancel order with current status: %(status)s.") % {'status': order.status}
            ]})

        order.status = OrderStatus.CANCELLED
        order.save(update_fields=['status'])
        return Response({"message": _("Order #%(number)s cancelled successfully.") % {'number': order.order_number}}, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Orders'],
        request=OrderStatusUpdateSerializer,
        responses={200: OrderDetailSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer},
        summary='Update order or payment status (Admin only)',
        description='Admins may update the order status, the payment status, or both in a single call.',
    )
    @action(detail=True, methods=['patch'], permission_classes=[IsAdminUser], url_path='status', url_name='status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data.get('status')
        new_payment = serializer.validated_data.get('payment_status')

        update_fields = []
        if new_status:
            order.status = new_status
            update_fields.append('status')
        if new_payment:
            order.payment_status = new_payment
            update_fields.append('payment_status')

        order.save(update_fields=update_fields)
        return Response(OrderDetailSerializer(order, context={'request': request}).data)
