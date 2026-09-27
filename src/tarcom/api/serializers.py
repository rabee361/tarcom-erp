from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from tarcom.base.models import CustomUser, OTPCode, UnitOfMeasure, MaterialCategory, Material
from tarcom.base.translation import *
from tarcom.utils.enums import UserType, CodeTypes
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
    """Allowed fields for the authenticated user's own profile (`/api/users/me/`)."""

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'phone', 'avatar']


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

