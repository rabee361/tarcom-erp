from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

from tarcom.base.models import Order, OrderStatus
from ..serializers import (
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    OrderStatusUpdateSerializer,
    MessageResponseSerializer,
    ErrorResponseSerializer,
)


@extend_schema_view(
    list=extend_schema(
        tags=['Orders'],
        summary='List orders',
        description='Buyers see only their own orders. Staff and admins see all orders across the system.',
        parameters=[
            OpenApiParameter(name='status', type=str, required=False, description='Filter by order status'),
            OpenApiParameter(name='payment_status', type=str, required=False, description='Filter by payment status'),
        ],
    ),
    retrieve=extend_schema(tags=['Orders'], summary='Retrieve order details with items'),
    create=extend_schema(tags=['Orders'], summary='Create/place an order (Checkout)'),
)
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['order_number', 'shipping_phone', 'user__email']
    ordering_fields = ['created_at', 'total_amount', 'status']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or getattr(user, 'is_admin', False):
            qs = Order.objects.all()
        else:
            qs = Order.objects.filter(user=user)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param.upper())
        payment_param = self.request.query_params.get('payment_status')
        if payment_param:
            qs = qs.filter(payment_status=payment_param.upper())
        return qs.select_related('user').prefetch_related('items__material', 'items__material__uom')

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
        description='Buyers can cancel their own order only while status is PENDING. Admins can cancel anytime prior to delivery.',
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
        return Response({"message": _("Order #%(number)s cancelled successfully.") % {'number': order.order_number}},
                        status=status.HTTP_200_OK)

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
