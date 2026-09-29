# Tarcom ERP - Complete Technical Implementation Blueprint

**Document Version:** 2.0  
**Target LLM:** Developer Agent  
**Context:** Tarcom ERP Django Backend & Administrative Web Dashboard (`d:\projects\tarcom`)  
**Scope:**
1. **Orders & OrderItems REST API** (`src/tarcom/api/`): Serializers, ViewSets, multi-material batch order creation, permissions, and URL routing.
2. **Dashboard Security & Authentication** (`src/tarcom/base/views/auth.py`): Dashboard login with 3-attempt lockout (15-minute cooldown via Django cache), logout, change password, and user/admin CRUD.
3. **Dashboard Core Business Management** (`src/tarcom/base/views/core.py` & `forms.py`): Dashboard stats overview, Materials CRUD, Categories CRUD, Units of Measure CRUD, and Orders management (list, detail, status updates).
4. **HTML UI Design System & Templates** (`src/tarcom/base/templates/`): Template hierarchy (`templates/users/`, `templates/materials/`, `templates/categories/`, `templates/units/`, `templates/orders/`) strictly adhering to `main.css` form grid styling and `change_password.html` design conventions.
5. **Quality Assurance & Verification**: Unit and integration test suites for both REST APIs and Dashboard views.

---

## 1. Architectural Map & Component Overview

```
d:\projects\tarcom\
├── plan.md                                        # Master Blueprint (this document)
└── src\tarcom\
    ├── api\
    │   ├── serializers.py                         # DRF Order, OrderItem, Favourites, Profile serializers
    │   ├── views\
    │   │   ├── auth.py                            # DRF Auth & Profile API ViewSets
    │   │   ├── core.py                            # DRF Materials, Categories, Units ViewSets
    │   │   ├── favourites.py                      # DRF Favourites ViewSet
    │   │   └── orders.py                          # DRF Orders & Batch Checkout ViewSet
    │   ├── urls.py                                # API DefaultRouter route definitions
    │   └── tests\
    │       ├── order_tests.py                     # API Order placement & permissions tests
    │       ├── favourite_tests.py                 # API Favourites tests
    │       └── profile_tests.py                   # API Profile tests
    └── base\
        ├── models.py                              # Order, OrderItem, FavouriteItem, Material, CustomUser
        ├── forms.py                               # Django Forms for Dashboard SSR
        ├── views\
        │   ├── auth.py                            # Dashboard Login (3-attempt limit), Logout, Users CRUD
        │   └── core.py                            # Dashboard Stats, Materials CRUD, Categories CRUD, Units CRUD, Orders
        ├── urls.py                                # Dashboard web routes
        └── templates\
            ├── base.html                          # Sidebar, header, theme toggle, script loader
            ├── login.html                         # Dashboard login with lockout & retry counter
            ├── dashboard.html                     # Overview dashboard
            ├── partials\
            │   └── dashboard_partial.html         # HTMX stats cards
            ├── users\
            │   ├── users_list.html                # Staff/Buyers listing
            │   ├── user_form.html                 # Add/Edit User (2-column form-grid)
            │   └── change_password.html           # Reference form layout
            ├── materials\
            │   ├── materials_list.html            # Products table with search/filters
            │   └── material_form.html             # Add/Edit Material with image preview
            ├── categories\
            │   ├── categories_list.html           # Tree/list of categories
            │   └── category_form.html             # Add/Edit Category
            ├── units\
            │   ├── units_list.html                # Units of measure table
            │   └── unit_form.html                 # Add/Edit Unit of Measure
            └── orders\
                ├── orders_list.html               # Orders history & status filter
                └── order_detail.html              # Order summary, items breakdown, status transition
```

---

## 2. Part 1: Orders & OrderItems REST API (`tarcom.api`)

### 2.1 Overview & Requirements
- Accept multiple materials in a single checkout payload (`items`: `[{material: id, quantity: num}, ...]`).
- Look up material price dynamically from `material.consumer_price` (preventing client-side price tampering).
- Validate material active status (`material.is_active=True`).
- Prevent duplicate material submissions within the same order.
- Calculate item `line_total = (quantity * unit_price) - discount_amount`.
- Calculate order `subtotal` and `total_amount = max(0, subtotal - discount_amount)`.
- Execute order creation and line items inside a database transaction (`transaction.atomic`).
- Auto-generate unique `order_number` (format: `ORD-YYYYMMDD-XXXX`).
- Permission scoping:
  - Authenticated regular buyers can only list and retrieve their own orders.
  - Staff / Admin users can list and retrieve all orders across the platform.
  - Buyers can cancel orders only when `status == PENDING`.
  - Admins can transition status (`PENDING -> CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED` or `CANCELLED`).

### 2.2 Serializers to Add in `src/tarcom/api/serializers.py`

```python
from decimal import Decimal
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from tarcom.base.models import Order, OrderItem, Material, CustomUser
from tarcom.utils.enums import OrderStatus, PaymentStatus, PaymentMethod


class OrderItemInputSerializer(serializers.Serializer):
    """Input representation for a single line item during checkout."""
    material = serializers.PrimaryKeyRelatedField(
        queryset=Material.objects.filter(is_active=True),
        help_text=_("ID of the active material to purchase.")
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0.001'),
        help_text=_("Quantity ordered (must be greater than 0).")
    )


class OrderItemReadSerializer(serializers.ModelSerializer):
    """Detailed read representation of an OrderItem."""
    material_name = serializers.CharField(source='material.name', read_only=True)
    material_image = serializers.ImageField(source='material.image1', read_only=True)
    uom_code = serializers.CharField(source='material.uom.code', read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id', 'material', 'material_name', 'material_image', 'uom_code',
            'quantity', 'unit_price', 'discount_amount', 'line_total'
        ]
        read_only_fields = fields


class OrderCreateSerializer(serializers.ModelSerializer):
    """
    Accepts multiple materials and checkout fields, creating Order and OrderItems atomically.
    """
    items = OrderItemInputSerializer(many=True, write_only=True, required=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'payment_method', 'shipping_address',
            'shipping_phone', 'notes', 'items', 'subtotal', 'discount_amount',
            'total_amount', 'created_at'
        ]
        read_only_fields = ['id', 'order_number', 'subtotal', 'discount_amount', 'total_amount', 'created_at']

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError(_("Order must contain at least one item."))
        # Verify no duplicate materials in the same payload
        material_ids = [item['material'].id for item in items]
        if len(material_ids) != len(set(material_ids)):
            raise serializers.ValidationError(_("Duplicate materials in a single order are not allowed."))
        return items

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        user = self.context['request'].user

        with transaction.atomic():
            order = Order.objects.create(
                user=user,
                status=OrderStatus.PENDING,
                payment_status=PaymentStatus.UNPAID,
                **validated_data
            )
            for item in items_data:
                mat = item['material']
                qty = item['quantity']
                price = mat.consumer_price or Decimal('0.00')
                OrderItem.objects.create(
                    order=order,
                    material=mat,
                    quantity=qty,
                    unit_price=price,
                    discount_amount=Decimal('0.00'),
                )
            # Recompute total amount
            order.calculate_totals(save_instance=True)
        return order


class OrderDetailSerializer(serializers.ModelSerializer):
    """Full detail view for an order including nested lines and customer metadata."""
    items = OrderItemReadSerializer(many=True, read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'user', 'user_email', 'user_name',
            'status', 'payment_method', 'payment_status',
            'shipping_address', 'shipping_phone', 'notes',
            'subtotal', 'discount_amount', 'total_amount',
            'items', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight summary serializer for order listings."""
    items_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status', 'payment_method', 'payment_status',
            'total_amount', 'items_count', 'created_at'
        ]
        read_only_fields = fields


class OrderStatusUpdateSerializer(serializers.Serializer):
    """Administrative serializer for transitioning order and payment statuses."""
    status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)
    payment_status = serializers.ChoiceField(choices=PaymentStatus.choices, required=False)

    def validate(self, attrs):
        if not attrs.get('status') and not attrs.get('payment_status'):
            raise serializers.ValidationError(_("At least one of status or payment_status must be provided."))
        return attrs
```

### 2.3 ViewSet Implementation: `OrderViewSet` (`src/tarcom/api/views/orders.py`)

Create `src/tarcom/api/views/orders.py`:

```python
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

from tarcom.base.models import Order
from tarcom.utils.enums import OrderStatus
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
        description='Buyers see only their own orders. Staff and administrators see all orders.',
        parameters=[
            OpenApiParameter(name='status', type=str, required=False, description='Filter by OrderStatus (e.g. PENDING, CONFIRMED)'),
            OpenApiParameter(name='payment_status', type=str, required=False, description='Filter by PaymentStatus (e.g. UNPAID, PAID)'),
        ],
    ),
    retrieve=extend_schema(tags=['Orders'], summary='Retrieve order details with line items'),
    create=extend_schema(tags=['Orders'], summary='Place a new order with multiple materials (Checkout)'),
)
class OrderViewSet(viewsets.ModelViewSet):
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
        description='Buyers can cancel their own order only while status is PENDING. Admins can cancel anytime before delivery.',
    )
    @action(detail=True, methods=['post'], url_path='cancel', url_name='cancel')
    def cancel(self, request, pk=None):
        order = self.get_object()
        user = request.user

        if not (user.is_staff or getattr(user, 'is_admin', False)):
            if order.status != OrderStatus.PENDING:
                return Response(
                    {"error": "Orders can only be cancelled while in PENDING status."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if order.status in [OrderStatus.DELIVERED, OrderStatus.CANCELLED]:
            return Response(
                {"error": f"Cannot cancel order with current status: {order.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = OrderStatus.CANCELLED
        order.save(update_fields=['status'])
        return Response({"message": f"Order #{order.order_number} cancelled successfully."}, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['Orders'],
        request=OrderStatusUpdateSerializer,
        responses={200: OrderDetailSerializer, 400: ErrorResponseSerializer, 403: ErrorResponseSerializer},
        summary='Update order or payment status (Admin only)',
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
```

---

## 3. Part 2: Dashboard Security, Authentication & Rate Limiting (`tarcom.base`)

### 3.1 Rate-Limiting Policy (3-Attempt Lockout)
- **Key Format**: `dashboard_login_attempts_{ip}_{identifier}`
- **Attempt Threshold**: 3 consecutive failed attempts.
- **Lockout Duration**: 15 minutes (900 seconds).
- **Behavior**:
  - Check before attempting authentication: if attempts $\ge 3$, reject immediately with:  
    `"لقد تم حظر المحاولات مؤقتاً بسبب تجاوز 3 محاولات خاطئة. يرجى المحاولة بعد 15 دقيقة."`
  - On failed credentials, increment attempt count with 900s TTL.
  - Remaining attempts warning displayed to user:  
    `"بيانات الدخول غير صحيحة. متبقي لديك {3 - attempts} محاولة."`
  - On successful login, clear cache key for both IP and identifier.
  - Check `user.is_staff or user.is_admin`: if user is not staff/admin, reject login with:  
    `"عذراً، هذا الحساب ليس لديه صلاحية الدخول إلى لوحة التحكم."`

### 3.2 Forms Implementation (`src/tarcom/base/forms.py`)

Create `src/tarcom/base/forms.py`:

```python
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from tarcom.base.models import CustomUser, Material, MaterialCategory, UnitOfMeasure, Order
from tarcom.utils.enums import OrderStatus, PaymentStatus, UserType


class DashboardLoginForm(forms.Form):
    phonenumber = forms.CharField(
        label=_("رقم الهاتف أو البريد الإلكتروني"),
        widget=forms.TextInput(attrs={
            'placeholder': _("رقم الهاتف أو البريد"),
            'class': 'form-control',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label=_("كلمة المرور"),
        widget=forms.PasswordInput(attrs={
            'placeholder': _("كلمة المرور"),
            'id': 'loginPassword',
            'class': 'form-control',
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        label=_("تذكرني"),
        widget=forms.CheckboxInput(attrs={'id': 'remember-me'})
    )


class DashboardChangePasswordForm(forms.Form):
    old_password = forms.CharField(
        label=_("كلمة المرور الحالية"),
        widget=forms.PasswordInput(attrs={'placeholder': _("كلمة المرور الحالية")})
    )
    new_password1 = forms.CharField(
        label=_("كلمة المرور الجديدة"),
        widget=forms.PasswordInput(attrs={'placeholder': _("كلمة المرور الجديدة")}),
        validators=[validate_password]
    )
    new_password2 = forms.CharField(
        label=_("تأكيد كلمة المرور الجديدة"),
        widget=forms.PasswordInput(attrs={'placeholder': _("تأكيد كلمة المرور الجديدة")})
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data.get('old_password')
        if not self.user.check_password(old_password):
            raise ValidationError(_("كلمة المرور الحالية غير صحيحة."))
        return old_password

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password1')
        p2 = cleaned_data.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError({'new_password2': _("كلمتا المرور غير متطابقتين.")})
        return cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data['new_password1'])
        self.user.save()
        return self.user


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label=_("كلمة المرور"),
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': _("كلمة المرور")})
    )
    confirm_password = forms.CharField(
        label=_("تأكيد كلمة المرور"),
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': _("تأكيد كلمة المرور")})
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name', 'phone', 'user_type', 'is_active', 'avatar']
        labels = {
            'email': _("البريد الإلكتروني"),
            'first_name': _("الاسم الأول"),
            'last_name': _("اسم العائلة"),
            'phone': _("رقم الهاتف"),
            'user_type': _("نوع المستخدم"),
            'is_active': _("الحساب نشط"),
            'avatar': _("الصورة الشخصية"),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        if not self.instance.pk and not password:
            self.add_error('password', _("كلمة المرور مطلوبة لإنشاء مستخدم جديد."))
        if password and password != confirm:
            self.add_error('confirm_password', _("كلمتا المرور غير متطابقتين."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            'name', 'name_en', 'name_ar',
            'category', 'uom',
            'supplier_price', 'consumer_price',
            'description', 'description_en', 'description_ar',
            'is_active', 'image1', 'image2'
        ]
        labels = {
            'name': _("اسم المادة"),
            'name_en': _("الاسم بالإنجليزية"),
            'name_ar': _("الاسم بالعربية"),
            'category': _("التصنيف"),
            'uom': _("وحدة القياس"),
            'supplier_price': _("سعر المورد"),
            'consumer_price': _("سعر المستهلك"),
            'description': _("الوصف"),
            'description_en': _("الوصف بالإنجليزية"),
            'description_ar': _("الوصف بالعربية"),
            'is_active': _("نشط"),
            'image1': _("الصورة الرئيسية"),
            'image2': _("صورة إضافية"),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = MaterialCategory
        fields = ['name', 'name_en', 'name_ar', 'parent']
        labels = {
            'name': _("اسم التصنيف"),
            'name_en': _("الاسم بالإنجليزية"),
            'name_ar': _("الاسم بالعربية"),
            'parent': _("التصنيف الرئيسي (اختياري)"),
        }


class UnitOfMeasureForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ['name', 'name_en', 'name_ar', 'code']
        labels = {
            'name': _("اسم الوحدة"),
            'name_en': _("الاسم بالإنجليزية"),
            'name_ar': _("الاسم بالعربية"),
            'code': _("رمز الوحدة (Code)"),
        }


class OrderDashboardStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=OrderStatus.choices,
        label=_("حالة الطلب"),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    payment_status = forms.ChoiceField(
        choices=PaymentStatus.choices,
        label=_("حالة الدفع"),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
```

### 3.3 Auth Views Implementation (`src/tarcom/base/views/auth.py`)

Implement `src/tarcom/base/views/auth.py`:

```python
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.cache import cache
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from tarcom.base.forms import DashboardLoginForm, DashboardChangePasswordForm, UserForm
from tarcom.base.models import CustomUser


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restricts access exclusively to staff/admin dashboard users."""
    login_url = reverse_lazy('login')

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_staff or getattr(user, 'is_admin', False))


class DashboardLoginView(View):
    template_name = "login.html"
    max_attempts = 3
    lockout_duration = 900  # 15 minutes

    def get(self, request):
        if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'is_admin', False)):
            return redirect('dashboard')
        form = DashboardLoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = DashboardLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        identifier = form.cleaned_data['phonenumber'].strip()
        password = form.cleaned_data['password']
        remember_me = form.cleaned_data.get('remember_me')
        ip = get_client_ip(request)
        cache_key = f"dash_login_attempts_{ip}_{identifier.lower()}"

        attempts = cache.get(cache_key, 0)
        if attempts >= self.max_attempts:
            messages.error(
                request,
                "لقد تم حظر المحاولات مؤقتاً لتجاوز 3 محاولات خاطئة. يرجى المحاولة بعد 15 دقيقة."
            )
            return render(request, self.template_name, {'form': form, 'locked': True})

        # Resolve user by email or phone
        user_obj = CustomUser.objects.filter(
            Q(email__iexact=identifier) | Q(phone=identifier)
        ).first()

        user = None
        if user_obj:
            user = authenticate(request, username=user_obj.email, password=password)

        if user is None:
            new_attempts = attempts + 1
            cache.set(cache_key, new_attempts, self.lockout_duration)
            remaining = self.max_attempts - new_attempts
            if remaining > 0:
                messages.error(request, f"بيانات الدخول غير صحيحة. متبقي لديك {remaining} محاولة.")
            else:
                messages.error(request, "تم استنفاد جميع المحاولات (3). تم قفل الحساب مؤقتاً لمدة 15 دقيقة.")
            return render(request, self.template_name, {'form': form})

        # Check admin/staff authorization
        if not (user.is_staff or getattr(user, 'is_admin', False)):
            messages.error(request, "عذراً، هذا الحساب ليس لديه صلاحية الدخول إلى لوحة التحكم.")
            return render(request, self.template_name, {'form': form})

        # Successful login: reset attempt count
        cache.delete(cache_key)
        login(request, user)
        if not remember_me:
            request.session.set_expiry(0)  # Expires on browser close
        else:
            request.session.set_expiry(1209600)  # 2 weeks

        next_url = request.GET.get('next') or reverse_lazy('dashboard')
        return redirect(next_url)


class DashboardLogoutView(View):
    def post(self, request):
        logout(request)
        return redirect('login')


class DashboardChangePasswordView(StaffRequiredMixin, View):
    template_name = "users/change_password.html"

    def get(self, request):
        form = DashboardChangePasswordForm(user=request.user)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = DashboardChangePasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تغيير كلمة المرور بنجاح. يرجى تسجيل الدخول مجدداً.")
            return redirect('login')
        return render(request, self.template_name, {'form': form})


class UsersListView(StaffRequiredMixin, ListView):
    model = CustomUser
    template_name = "users/users_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        qs = CustomUser.objects.all().order_by('-date_joined')
        user_type = self.request.GET.get('user_type')
        if user_type:
            qs = qs.filter(user_type=user_type)
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q))
        return qs


class UserCreateView(StaffRequiredMixin, CreateView):
    model = CustomUser
    form_class = UserForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy('users-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء المستخدم بنجاح.")
        return super().form_valid(form)


class UserUpdateView(StaffRequiredMixin, UpdateView):
    model = CustomUser
    form_class = UserForm
    template_name = "users/user_form.html"
    success_url = reverse_lazy('users-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تحديث بيانات المستخدم بنجاح.")
        return super().form_valid(form)


class UserDeleteView(StaffRequiredMixin, DeleteView):
    model = CustomUser
    template_name = "users/user_confirm_delete.html"
    success_url = reverse_lazy('users-list')

    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            messages.error(request, "لا يمكنك حذف حسابك الحالي أثناء تسجيل الدخول.")
            return redirect('users-list')
        messages.success(request, "تم حذف المستخدم بنجاح.")
        return super().delete(request, *args, **kwargs)
```

---

## 4. Part 3: Core Dashboard Views (`tarcom.base.views.core`)

### 4.1 Dashboard Overview & Operations
In `src/tarcom/base/views/core.py`, provide:
1. `DashboardView` & `DashboardPartialView`:
   - Pass dynamic aggregate counts for products, categories, new orders, clients, warehouses, and revenue.
2. `MaterialListView`, `MaterialCreateView`, `MaterialUpdateView`, `MaterialDeleteView`.
3. `CategoryListView`, `CategoryCreateView`, `CategoryUpdateView`, `CategoryDeleteView`.
4. `UnitListView`, `UnitCreateView`, `UnitUpdateView`, `UnitDeleteView`.
5. `OrderListView`, `OrderDetailView`, `OrderStatusUpdateView`.

```python
from decimal import Decimal
from django.contrib import messages
from django.db.models import Sum, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from tarcom.base.forms import (
    MaterialForm, CategoryForm, UnitOfMeasureForm, OrderDashboardStatusForm
)
from tarcom.base.models import (
    Material, MaterialCategory, UnitOfMeasure, Order, OrderItem, CustomUser
)
from tarcom.utils.enums import OrderStatus, UserType
from .auth import StaffRequiredMixin


class DashboardView(StaffRequiredMixin, View):
    def get(self, request):
        return render(request, "dashboard.html")


class DashboardPartialView(StaffRequiredMixin, View):
    """HTMX stats grid fragment."""
    def get(self, request):
        context = {
            "products_count": Material.objects.count(),
            "categories_count": MaterialCategory.objects.count(),
            "orders_count": Order.objects.filter(status=OrderStatus.PENDING).count(),
            "clients_count": CustomUser.objects.filter(user_type=UserType.BUYER).count(),
            "admins_count": CustomUser.objects.filter(is_staff=True).count(),
            "total_sales": Order.objects.exclude(status=OrderStatus.CANCELLED).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00'),
        }
        return render(request, "partials/dashboard_partial.html", context=context)


# ==========================================
# Materials Management
# ==========================================

class MaterialListView(StaffRequiredMixin, ListView):
    model = Material
    template_name = "materials/materials_list.html"
    context_object_name = "materials"
    paginate_by = 20

    def get_queryset(self):
        qs = Material.objects.select_related('category', 'uom').all().order_by('-created_at')
        q = self.request.GET.get('q')
        cat_id = self.request.GET.get('category')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q) | Q(name_ar__icontains=q))
        if cat_id:
            qs = qs.filter(category_id=cat_id)
        return qs


class MaterialCreateView(StaffRequiredMixin, CreateView):
    model = Material
    form_class = MaterialForm
    template_name = "materials/material_form.html"
    success_url = reverse_lazy('materials-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إضافة المادة بنجاح.")
        return super().form_valid(form)


class MaterialUpdateView(StaffRequiredMixin, UpdateView):
    model = Material
    form_class = MaterialForm
    template_name = "materials/material_form.html"
    success_url = reverse_lazy('materials-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تعديل المادة بنجاح.")
        return super().form_valid(form)


class MaterialDeleteView(StaffRequiredMixin, DeleteView):
    model = Material
    template_name = "materials/material_confirm_delete.html"
    success_url = reverse_lazy('materials-list')


# ==========================================
# Categories Management
# ==========================================

class CategoryListView(StaffRequiredMixin, ListView):
    model = MaterialCategory
    template_name = "categories/categories_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return MaterialCategory.objects.select_related('parent').all().order_by('name')


class CategoryCreateView(StaffRequiredMixin, CreateView):
    model = MaterialCategory
    form_class = CategoryForm
    template_name = "categories/category_form.html"
    success_url = reverse_lazy('categories-list')


class CategoryUpdateView(StaffRequiredMixin, UpdateView):
    model = MaterialCategory
    form_class = CategoryForm
    template_name = "categories/category_form.html"
    success_url = reverse_lazy('categories-list')


class CategoryDeleteView(StaffRequiredMixin, DeleteView):
    model = MaterialCategory
    template_name = "categories/category_confirm_delete.html"
    success_url = reverse_lazy('categories-list')


# ==========================================
# Units of Measure Management
# ==========================================

class UnitListView(StaffRequiredMixin, ListView):
    model = UnitOfMeasure
    template_name = "units/units_list.html"
    context_object_name = "units"


class UnitCreateView(StaffRequiredMixin, CreateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "units/unit_form.html"
    success_url = reverse_lazy('units-list')


class UnitUpdateView(StaffRequiredMixin, UpdateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "units/unit_form.html"
    success_url = reverse_lazy('units-list')


class UnitDeleteView(StaffRequiredMixin, DeleteView):
    model = UnitOfMeasure
    template_name = "units/unit_confirm_delete.html"
    success_url = reverse_lazy('units-list')


# ==========================================
# Orders Management
# ==========================================

class OrderListView(StaffRequiredMixin, ListView):
    model = Order
    template_name = "orders/orders_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.select_related('user').all().order_by('-created_at')
        status_param = self.request.GET.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(order_number__icontains=q) | Q(user__email__icontains=q) | Q(shipping_phone__icontains=q))
        return qs


class OrderDetailView(StaffRequiredMixin, DetailView):
    model = Order
    template_name = "orders/order_detail.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_form'] = OrderDashboardStatusForm(initial={
            'status': self.object.status,
            'payment_status': self.object.payment_status
        })
        return ctx


class OrderStatusUpdateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderDashboardStatusForm(request.POST)
        if form.is_valid():
            order.status = form.cleaned_data['status']
            order.payment_status = form.cleaned_data['payment_status']
            order.save(update_fields=['status', 'payment_status'])
            messages.success(request, f"تم تحديث حالة الطلب #{order.order_number} بنجاح.")
        return redirect('order-detail', pk=order.pk)
```

---

## 5. Part 4: Template Design System & CSS Layout Guide

All form pages must mirror `src/tarcom/base/templates/users/change_password.html` and use classes from `src/tarcom/base/static/assets/css/main.css`.

### 5.1 Canonical Form Layout Architecture

```html
{% extends 'base.html' %}
{% load static %}

{% block title %}{{ title }}{% endblock %}

{% block content %}
<div class="content-header">
    <nav class="breadcrumb">
        <a href="{% url 'dashboard' %}">لوحة التحكم</a>
        <i class="separator fas fa-chevron-left"></i>
        <a href="{% url 'module-list' %}">{{ module_name }}</a>
        <i class="separator fas fa-chevron-left"></i>
        <span>{{ action_name }}</span>
    </nav>
</div>

<div class="content-body">
    <form method="post" enctype="multipart/form-data">
        {% csrf_token %}
        <div class="form-container">
            <div class="form-grid">
                <!-- Column 1 -->
                <div class="form-section">
                    <div class="form-group">
                        <label>{{ form.field1.label }}</label>
                        {{ form.field1 }}
                        {% if form.field1.errors %}
                            <div class="error">{{ form.field1.errors }}</div>
                        {% endif %}
                    </div>
                </div>

                <!-- Column 2 -->
                <div class="form-section">
                    <div class="form-group image-picker">
                        <label>{{ form.image1.label }}</label>
                        {{ form.image1 }}
                        <div class="image-preview">
                            <img id="image-preview" width="100" height="100" src="{% if form.instance.image1 %}{{ form.instance.image1.url }}{% endif %}" alt="Preview">
                        </div>
                    </div>
                </div>
            </div>

            {% if form.non_field_errors %}
                <div class="error-message">
                    {% for error in form.non_field_errors %}
                        {{ error }}
                    {% endfor %}
                </div>
            {% endif %}
        </div>

        <div class="form-button-container">
            <button type="submit" class="btn btn-primary">حفظ</button>
            <a href="{% url 'module-list' %}" class="btn btn-secondary">إلغاء</a>
        </div>
    </form>
</div>
{% endblock %}
```

### 5.2 Template File Inventory to Create
1. **`src/tarcom/base/templates/login.html`**: Update existing template to render Django messages (lockout warning, remaining attempts countdown, retry alert).
2. **`src/tarcom/base/templates/users/users_list.html`**: Table showing email, full name, phone, user type, status, actions (edit, delete, change password).
3. **`src/tarcom/base/templates/users/user_form.html`**: Add/edit user form.
4. **`src/tarcom/base/templates/users/user_confirm_delete.html`**: Confirmation prompt for deleting a user.
5. **`src/tarcom/base/templates/materials/materials_list.html`**: Product grid or table with image, name, category, UOM, prices, and status.
6. **`src/tarcom/base/templates/materials/material_form.html`**: Add/edit material form with live image preview.
7. **`src/tarcom/base/templates/materials/material_confirm_delete.html`**: Delete material confirmation.
8. **`src/tarcom/base/templates/categories/categories_list.html` & `category_form.html`**.
9. **`src/tarcom/base/templates/units/units_list.html` & `unit_form.html`**.
10. **`src/tarcom/base/templates/orders/orders_list.html`**: Orders table with filters for status (Pending, Confirmed, Shipped, Delivered, Cancelled) and search by order number or customer phone.
11. **`src/tarcom/base/templates/orders/order_detail.html`**: Order summary, shipping address, line items table (material, UOM, unit price, quantity, line total), subtotal, discount, total amount, and inline status update form.

---

## 6. Part 5: URL Route Mapping

### 6.1 API Routes (`src/tarcom/api/urls.py`)
```python
router.register(r'orders', OrderViewSet, basename='orders')
```
Provides:
- `POST /api/orders/`: Place multi-material order
- `GET /api/orders/`: List user orders (or all if admin)
- `GET /api/orders/{id}/`: Order details
- `POST /api/orders/{id}/cancel/`: Cancel order
- `PATCH /api/orders/{id}/status/`: Admin status change

### 6.2 Base Dashboard Routes (`src/tarcom/base/urls.py`)
```python
from django.urls import path
from .views.auth import (
    DashboardLoginView, DashboardLogoutView, DashboardChangePasswordView,
    UsersListView, UserCreateView, UserUpdateView, UserDeleteView
)
from .views.core import (
    DashboardView, DashboardPartialView,
    MaterialListView, MaterialCreateView, MaterialUpdateView, MaterialDeleteView,
    CategoryListView, CategoryCreateView, CategoryUpdateView, CategoryDeleteView,
    UnitListView, UnitCreateView, UnitUpdateView, UnitDeleteView,
    OrderListView, OrderDetailView, OrderStatusUpdateView
)

urlpatterns = [
    # Auth
    path("login/", DashboardLoginView.as_view(), name="login"),
    path("logout/", DashboardLogoutView.as_view(), name="logout"),
    path("change-password/", DashboardChangePasswordView.as_view(), name="change-password"),

    # Dashboard Overview
    path("", DashboardView.as_view(), name="home"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/partial/", DashboardPartialView.as_view(), name="dashboard-partial"),

    # Users
    path("dashboard/users/", UsersListView.as_view(), name="users-list"),
    path("dashboard/users/create/", UserCreateView.as_view(), name="user-create"),
    path("dashboard/users/<int:pk>/edit/", UserUpdateView.as_view(), name="user-edit"),
    path("dashboard/users/<int:pk>/delete/", UserDeleteView.as_view(), name="user-delete"),

    # Materials
    path("dashboard/materials/", MaterialListView.as_view(), name="materials-list"),
    path("dashboard/materials/create/", MaterialCreateView.as_view(), name="material-create"),
    path("dashboard/materials/<int:pk>/edit/", MaterialUpdateView.as_view(), name="material-edit"),
    path("dashboard/materials/<int:pk>/delete/", MaterialDeleteView.as_view(), name="material-delete"),

    # Categories
    path("dashboard/categories/", CategoryListView.as_view(), name="categories-list"),
    path("dashboard/categories/create/", CategoryCreateView.as_view(), name="category-create"),
    path("dashboard/categories/<int:pk>/edit/", CategoryUpdateView.as_view(), name="category-edit"),
    path("dashboard/categories/<int:pk>/delete/", CategoryDeleteView.as_view(), name="category-delete"),

    # Units
    path("dashboard/units/", UnitListView.as_view(), name="units-list"),
    path("dashboard/units/create/", UnitCreateView.as_view(), name="unit-create"),
    path("dashboard/units/<int:pk>/edit/", UnitUpdateView.as_view(), name="unit-edit"),
    path("dashboard/units/<int:pk>/delete/", UnitDeleteView.as_view(), name="unit-delete"),

    # Orders
    path("dashboard/orders/", OrderListView.as_view(), name="orders-list"),
    path("dashboard/orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("dashboard/orders/<int:pk>/status/", OrderStatusUpdateView.as_view(), name="order-status-update"),
]
```

---

## 7. Part 6: Step-by-Step Implementation Sequence for Next LLM

Execute the following 12 atomic steps in order:

| Step | Action | Target Files |
|------|--------|--------------|
| **1** | Implement Order Serializers | `src/tarcom/api/serializers.py` (`OrderItemInputSerializer`, `OrderCreateSerializer`, `OrderDetailSerializer`, etc.) |
| **2** | Implement Order API ViewSet | `src/tarcom/api/views/orders.py` |
| **3** | Register Order Route in API Router | `src/tarcom/api/urls.py` |
| **4** | Create Dashboard Forms | `src/tarcom/base/forms.py` (Login, ChangePassword, User, Material, Category, Unit, OrderStatus) |
| **5** | Implement Dashboard Auth Views & Lockout | `src/tarcom/base/views/auth.py` (3-attempt cache check, login, logout, users CRUD) |
| **6** | Implement Dashboard Core Views | `src/tarcom/base/views/core.py` (Materials, Categories, Units, Orders) |
| **7** | Configure Dashboard URL Patterns | `src/tarcom/base/urls.py` |
| **8** | Update `login.html` Template | `src/tarcom/base/templates/login.html` (add Django messages for remaining attempts & lockout) |
| **9** | Create Users Templates | `src/tarcom/base/templates/users/users_list.html`, `user_form.html`, `user_confirm_delete.html` |
| **10** | Create Materials Templates | `src/tarcom/base/templates/materials/materials_list.html`, `material_form.html`, `material_confirm_delete.html` |
| **11** | Create Categories & Units Templates | `src/tarcom/base/templates/categories/`, `src/tarcom/base/templates/units/` |
| **12** | Create Orders Templates | `src/tarcom/base/templates/orders/orders_list.html`, `order_detail.html` |
| **13** | Run & Verify Test Suites | Terminal: `uv run python src/tarcom/manage.py test tarcom.api tarcom.base` |

---

## 8. Part 7: Test Coverage Specifications

1. **`src/tarcom/api/tests/order_tests.py`**:
   - `test_order_creation_multiple_materials_success`: Submits 3 active materials, verifies line items, quantities, prices from `consumer_price`, subtotal, and total calculation.
   - `test_order_creation_duplicate_material_fails`: Validates payload rejecting duplicate materials.
   - `test_order_creation_inactive_material_fails`: Returns 400.
   - `test_buyer_isolated_from_other_orders`: Verifies buyer cannot retrieve another user's order.
   - `test_buyer_cancel_pending_order`: Allowed.
   - `test_buyer_cannot_cancel_shipped_order`: Returns 400.
   - `test_admin_status_transition`: Admin updates order status to `PROCESSING` and payment to `PAID`.

2. **`src/tarcom/base/tests.py` (Dashboard Tests)**:
   - `test_dashboard_login_success`: Valid staff credentials redirect to `/dashboard/`.
   - `test_dashboard_login_rate_limiting`: 3 failed attempts lock out user for 15 minutes and display error message.
   - `test_non_staff_redirected_from_dashboard`: Regular buyers redirected to `/login/?next=...`.
   - `test_dashboard_materials_crud`: Create, edit, and delete material via dashboard forms.
   - `test_dashboard_orders_status_update`: Staff can update order status via `OrderStatusUpdateView`.
