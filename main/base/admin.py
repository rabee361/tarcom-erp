from django.contrib import admin
from .models import (
    UnitOfMeasure,
    MaterialCategory,
    Material,
    Warehouse,
    WarehouseStock,
    StockMovement,
    Account,
    JournalEntry,
    JournalEntryLine,
    BusinessPartner,
    InvoiceType,
    Invoice,
    InvoiceMaterial,
    Payment,
    Setting,
)


class InvoiceMaterialInline(admin.TabularInline):
    model = InvoiceMaterial
    extra = 1


class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 2


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'uom', 'cost_price', 'selling_price', 'reorder_level', 'is_active')
    list_filter = ('category', 'uom', 'is_active')
    search_fields = ('name', 'code')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'location', 'is_active')
    search_fields = ('name', 'code')


@admin.register(WarehouseStock)
class WarehouseStockAdmin(admin.ModelAdmin):
    list_display = ('warehouse', 'material', 'quantity')
    list_filter = ('warehouse',)
    search_fields = ('material__name', 'material__code', 'warehouse__name')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('movement_type', 'material', 'warehouse', 'quantity', 'unit_cost', 'reference_number', 'created_at')
    list_filter = ('movement_type', 'warehouse', 'created_at')
    search_fields = ('material__name', 'material__code', 'reference_number')


@admin.register(BusinessPartner)
class BusinessPartnerAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_customer', 'is_supplier', 'tax_number', 'phone', 'email', 'is_active')
    list_filter = ('is_customer', 'is_supplier', 'is_active')
    search_fields = ('name', 'tax_number', 'phone', 'email')


@admin.register(InvoiceType)
class InvoiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'direction', 'affects_inventory', 'affects_accounting')
    list_filter = ('direction', 'affects_inventory', 'affects_accounting')


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'invoice_type', 'partner', 'invoice_date', 'status', 'total_amount', 'paid_amount')
    list_filter = ('status', 'invoice_type', 'invoice_date')
    search_fields = ('invoice_number', 'partner__name')
    inlines = [InvoiceMaterialInline]


@admin.register(InvoiceMaterial)
class InvoiceMaterialAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'material', 'quantity', 'unit_price', 'line_total')
    search_fields = ('invoice__invoice_number', 'material__name', 'material__code')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_number', 'payment_date', 'partner', 'payment_method', 'amount', 'account')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('payment_number', 'partner__name', 'reference')


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'parent', 'balance', 'is_active')
    list_filter = ('account_type', 'is_active')
    search_fields = ('code', 'name')


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('entry_number', 'entry_date', 'status', 'description', 'origin_type')
    list_filter = ('status', 'entry_date')
    search_fields = ('entry_number', 'description')
    inlines = [JournalEntryLineInline]


@admin.register(JournalEntryLine)
class JournalEntryLineAdmin(admin.ModelAdmin):
    list_display = ('journal_entry', 'account', 'debit', 'credit', 'memo')
    search_fields = ('journal_entry__entry_number', 'account__name', 'memo')


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'description')
    search_fields = ('key',)