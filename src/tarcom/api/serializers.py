from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from tarcom.base.models import CustomUser, OTPCode
from tarcom.utils.enums import UserType, CodeTypes
from tarcom.utils.helper import generate_code, get_expiration_time, send_otp_email
from django.utils import timezone
from django.core.signing import TimestampSigner


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'avatar', 'user_type', 'is_verified']
        read_only_fields = ['id', 'is_verified']


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
            )
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
