from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import *


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'user_type', 'is_verified', 'is_staff')
    list_filter = ('user_type', 'is_verified', 'is_staff', 'is_superuser')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone', 'avatar', 'user_type', 'is_verified')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ('email', 'code', 'code_type', 'is_used', 'expires_at', 'created_at')
    list_filter = ('code_type', 'is_used')
    search_fields = ('email', 'code')


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(UnitConversion)
class UnitConversionAdmin(admin.ModelAdmin):
    list_display = ('from_uom', 'to_uom', 'factor')


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'uom', 'supplier_price', 'consumer_price', 'is_active')
    list_filter = ('category', 'uom', 'is_active')
    search_fields = ('name',)


@admin.register(FavouriteItem)
class FavouriteItemAdmin(admin.ModelAdmin):
    list_display = ('user', 'material', 'created_at')
    search_fields = ('user__email', 'material__name')


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')
    search_fields = ('key',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    readonly_fields = ('line_total',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'status', 'payment_status', 'payment_method', 'total_amount', 'created_at')
    list_filter = ('status', 'payment_status', 'payment_method', 'created_at')
    search_fields = ('order_number', 'user__email', 'shipping_phone')
    readonly_fields = ('order_number', 'subtotal', 'total_amount', 'created_at', 'updated_at')
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'material', 'quantity', 'unit_price', 'discount_amount', 'line_total')
    list_filter = ('created_at',)
    search_fields = ('order__order_number', 'material__name')
    readonly_fields = ('line_total',)