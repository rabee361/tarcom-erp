from decimal import Decimal

from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema_field
from tarcom.base.models import (
    CustomUser,
    OTPCode,
    UnitOfMeasure,
    MaterialCategory,
    Material,
    FavouriteItem,
    Order,
    OrderItem,
)
from tarcom.base.translation import *
from tarcom.utils.enums import UserType, CodeTypes, OrderStatus, PaymentStatus
from tarcom.utils.helper import generate_code, get_expiration_time, send_otp_email
from django.utils import timezone
from django.core.signing import TimestampSigner
from django.conf import settings


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'avatar', 'user_type', 'is_verified']
        read_only_fields = ['id', 'is_verified', 'user_type']


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Allowed fields for the authenticated user's own profile (`/api/users/me/`).
    Includes avatar format and file size validation (<= 2MB).
    """

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'phone', 'avatar']

    def validate_avatar(self, value):
        if value:
            # 2MB size limit
            if value.size > 2 * 1024 * 1024:
                raise serializers.ValidationError(_("Avatar size cannot exceed 2MB."))
            allowed_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.jfif')
            if not value.name.lower().endswith(allowed_extensions):
                raise serializers.ValidationError(
                    _("Avatar file must be one of: JPG, JPEG, PNG, WEBP, JFIF.")
                )
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for authenticated user changing password.
    Requires current password confirmation and new password validation.
    """
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Current password is incorrect."))
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": _("Passwords do not match.")})
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({"new_password": _("New password cannot be the same as current password.")})
        return attrs

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class AccountDeactivateSerializer(serializers.Serializer):
    password = serializers.CharField(required=True, write_only=True)

    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Password is incorrect."))
        return value


# ==========================================
# OpenAPI response serializers
# ==========================================

class MessageResponseSerializer(serializers.Serializer):
    """Standard informational response: {"message": "..."}"""
    message = serializers.CharField()


class SignupResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    email = serializers.EmailField()


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class TokenResponseSerializer(serializers.Serializer):
    """JWT payload returned by login and signup verification."""
    tokens = TokenPairSerializer()
    user = UserSerializer()
    message = serializers.CharField(required=False)


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField(required=False)


class VerifyOtpResponseSerializer(serializers.Serializer):
    """
    Verify-OTP response.
    SIGNUP flow returns `tokens` + `user`; password flows return a signed `reset_token`.
    """
    message = serializers.CharField()
    tokens = TokenPairSerializer(required=False)
    user = UserSerializer(required=False)
    reset_token = serializers.CharField(required=False)


class ErrorResponseSerializer(serializers.Serializer):
    """Loose schema for DRF validation and permission error payloads."""
    detail = serializers.CharField(required=False)
    error = serializers.CharField(required=False)
    non_field_errors = serializers.ListField(child=serializers.CharField(), required=False)


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=150, required=False, default='')
    last_name = serializers.CharField(max_length=150, required=False, default='')
    phone = serializers.CharField(max_length=20, required=False, default='')
    user_type = serializers.ChoiceField(choices=UserType.choices, default=UserType.BUYER)

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=validated_data.get('phone', ''),
            user_type=validated_data.get('user_type', UserType.BUYER),
            is_verified=False,
        )
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_verified:
            raise serializers.ValidationError(
                {"error": "Account not verified", "needs_verification": True, "email": email},
                code='unverified_account'
            ) ## should be removed
        attrs['user'] = user
        return attrs


class SendOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code_type = serializers.ChoiceField(choices=CodeTypes.choices)

    def validate_email(self, value):
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value

    def validate(self, attrs):
        email = attrs['email']
        if OTPCode.check_limit(email):
            raise serializers.ValidationError("Too many OTP requests. Please try again later.")
        return attrs


class VerifyOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.IntegerField()
    code_type = serializers.ChoiceField(choices=CodeTypes.choices)

    def validate(self, attrs):
        email = attrs['email']
        code = attrs['code']
        code_type = attrs['code_type']
        otp = OTPCode.objects.filter(
            email=email, code=code, code_type=code_type, is_used=False
        ).first()
        if not otp:
            raise serializers.ValidationError("Invalid or already used OTP code.")
        if otp.is_expired:
            raise serializers.ValidationError("OTP code has expired.")
        attrs['otp'] = otp
        return attrs


class ForgetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.IntegerField(required=False)
    reset_token = serializers.CharField(required=False)
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()

    def validate(self, attrs):
        if attrs.get('new_password') != attrs.get('new_password_confirm'):
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        if not attrs.get('code') and not attrs.get('reset_token'):
            raise serializers.ValidationError("Either code or reset_token must be provided.")
        return attrs


class TranslateModelSerializer(serializers.ModelSerializer):
    """
    Base serializer integrating with django-modeltranslation TranslationOptions.
    Automatically discovers and includes translated fields (e.g. name_en, name_ar)
    based on the specified translation_options.
    """
    translation_options = None

    def get_field_names(self, declared_fields, info):
        fields = super().get_field_names(declared_fields, info)
        if self.translation_options:
            lang_codes = [lang[0] for lang in getattr(settings, 'LANGUAGES', [('en', 'en'), ('ar', 'ar')])]
            trans_fields = getattr(self.translation_options, 'fields', ())
            for f in trans_fields:
                for lang in lang_codes:
                    field_lang = f"{f}_{lang}"
                    if field_lang not in fields and hasattr(self.Meta.model, field_lang):
                        fields.append(field_lang)
        return fields

    def build_standard_field(self, field_name, model_field):
        field_class, field_kwargs = super().build_standard_field(field_name, model_field)
        if self.translation_options:
            lang_codes = [lang[0] for lang in getattr(settings, 'LANGUAGES', [('en', 'en'), ('ar', 'ar')])]
            trans_fields = getattr(self.translation_options, 'fields', ())
            for f in trans_fields:
                for lang in lang_codes:
                    if field_name == f"{f}_{lang}":
                        field_kwargs['required'] = False
                        field_kwargs['allow_blank'] = True
                        field_kwargs['allow_null'] = True
        return field_class, field_kwargs

    def to_internal_value(self, data):
        if hasattr(data, 'copy'):
            data = data.copy()
        elif isinstance(data, dict):
            data = dict(data)

        if self.translation_options and isinstance(data, dict):
            trans_fields = getattr(self.translation_options, 'fields', ())
            default_lang = getattr(settings, 'MODELTRANSLATION_DEFAULT_LANGUAGE', 'en')
            for f in trans_fields:
                if not data.get(f):
                    default_key = f"{f}_{default_lang}"
                    if data.get(default_key):
                        data[f] = data[default_key]
                    else:
                        for k, v in data.items():
                            if k.startswith(f"{f}_") and v:
                                data[f] = v
                                break
                default_key = f"{f}_{default_lang}"
                if data.get(f) and not data.get(default_key):
                    data[default_key] = data[f]

        return super().to_internal_value(data)


class UnitOfMeasureSerializer(TranslateModelSerializer):
    translation_options = UnitOfMeasureTranslationOptions

    class Meta:
        model = UnitOfMeasure
        fields = ['id', 'name', 'name_en', 'name_ar', 'code', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class MaterialCategoryChildSerializer(TranslateModelSerializer):
    translation_options = MaterialCategoryTranslationOptions

    class Meta:
        model = MaterialCategory
        fields = ['id', 'name', 'name_en', 'name_ar', 'parent']


class MaterialCategorySerializer(TranslateModelSerializer):
    translation_options = MaterialCategoryTranslationOptions
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = MaterialCategory
        fields = ['id', 'name', 'name_en', 'name_ar', 'parent', 'subcategories', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(MaterialCategoryChildSerializer(many=True))
    def get_subcategories(self, obj):
        children = obj.subcategories.all()
        return MaterialCategoryChildSerializer(children, many=True, context=self.context).data


class MaterialSerializer(TranslateModelSerializer):
    translation_options = MaterialTranslationOptions
    category_name = serializers.CharField(source='category.name', read_only=True)
    uom_name = serializers.CharField(source='uom.name', read_only=True)
    category_detail = MaterialCategoryChildSerializer(source='category', read_only=True)
    uom_detail = UnitOfMeasureSerializer(source='uom', read_only=True)

    class Meta:
        model = Material
        fields = [
            'id',
            'name', 'name_en', 'name_ar',
            'description', 'description_en', 'description_ar',
            'category', 'category_name', 'category_detail',
            'uom', 'uom_name', 'uom_detail',
            'supplier_price', 'consumer_price',
            'is_active', 'expire_date',
            'spec_key1', 'spec_key2', 'spec_key3', 'spec_key4', 'spec_key5',
            'spec_val1', 'spec_val2', 'spec_val3', 'spec_val4', 'spec_val5',
            'image1', 'image2', 'image3', 'image4', 'image5',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SettingSerializer(TranslateModelSerializer):
    translation_options = SettingTranslationOptions

    class Meta:
        model = Setting
        fields = ['key','value','description']


# ==========================================
# Favourites
# ==========================================

class MaterialCompactSerializer(serializers.ModelSerializer):
    """Lightweight material representation for favourite and order item listings."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    uom_name = serializers.CharField(source='uom.name', read_only=True)

    class Meta:
        model = Material
        fields = [
            'id', 'name', 'consumer_price', 'supplier_price',
            'is_active', 'image1', 'category', 'category_name', 'uom', 'uom_name'
        ]


class FavouriteItemSerializer(serializers.ModelSerializer):
    """Read serializer with nested material details."""
    material_detail = MaterialCompactSerializer(source='material', read_only=True)

    class Meta:
        model = FavouriteItem
        fields = ['id', 'material', 'material_detail', 'created_at']
        read_only_fields = ['id', 'created_at']


class FavouriteCreateSerializer(serializers.Serializer):
    """Write serializer for adding a material to favourites."""
    material = serializers.PrimaryKeyRelatedField(
        queryset=Material.objects.filter(is_active=True),
        help_text=_("ID of the active material to favourite.")
    )

    def validate_material(self, material):
        user = self.context['request'].user
        if FavouriteItem.objects.filter(user=user, material=material).exists():
            raise serializers.ValidationError(_("Material is already in your favourites."))
        return material

    def create(self, validated_data):
        user = self.context['request'].user
        return FavouriteItem.objects.create(user=user, material=validated_data['material'])


class FavouriteToggleResponseSerializer(serializers.Serializer):
    is_favourite = serializers.BooleanField()
    message = serializers.CharField()


# ==========================================
# Orders & Order Items
# ==========================================

class OrderItemReadSerializer(serializers.ModelSerializer):
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


class OrderItemInputSerializer(serializers.Serializer):
    material = serializers.PrimaryKeyRelatedField(
        queryset=Material.objects.filter(is_active=True),
        help_text=_("ID of the active material to purchase.")
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal('0.001'),
        required=True,
        help_text=_("Quantity ordered (must be greater than 0).")
    )


class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemInputSerializer(many=True, write_only=True, required=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'payment_method', 'shipping_address',
            'shipping_phone', 'notes', 'items', 'subtotal', 'discount_amount',
            'total_amount', 'created_at'
        ]
        read_only_fields = ['id', 'order_number', 'subtotal', 'discount_amount',
                            'total_amount', 'created_at']

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError(_("Order must contain at least one item."))
        # Verify no duplicate materials in the single submission
        material_ids = [item['material'].id for item in items]
        if len(material_ids) != len(set(material_ids)):
            raise serializers.ValidationError(_("Duplicate materials in single order are not allowed."))
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
            order.calculate_totals(save_instance=True)
        return order


class OrderDetailSerializer(serializers.ModelSerializer):
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

    @extend_schema_field(serializers.CharField())
    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email


class OrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.IntegerField(source='items.count', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status', 'payment_method', 'payment_status',
            'total_amount', 'items_count', 'created_at'
        ]
        read_only_fields = fields


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)
    payment_status = serializers.ChoiceField(choices=PaymentStatus.choices, required=False)

    def validate(self, attrs):
        if not attrs.get('status') and not attrs.get('payment_status'):
            raise serializers.ValidationError(
                _("At least one of status or payment_status must be provided.")
            )
        return attrs

