from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from tarcom.utils.enums import *


class TimeStampModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ==========================================
# 1. Master Data: Products & Warehouses
# ==========================================

class UnitOfMeasure(TimeStampModel):
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=20, unique=True)

    class Meta:
        verbose_name = _("Unit of Measure")
        verbose_name_plural = _("Units of Measure")
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

class UnitConversion(TimeStampModel):
    from_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.CASCADE, related_name='conversions_from')
    to_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.CASCADE, related_name='conversions_to')
    factor = models.DecimalField(max_digits=12, decimal_places=6)

    class Meta:
        unique_together = ('from_uom', 'to_uom')
        verbose_name = _("Unit Conversion")
        verbose_name_plural = _("Unit Conversions")

    def clean(self):
        if self.from_uom == self.to_uom:
            raise ValidationError(_("From and To units of measure must be different."))

    def __str__(self):
        return f"1 {self.from_uom.code} = {self.factor} {self.to_uom.code}"

class MaterialCategory(TimeStampModel):
    name = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories'
    )

    class Meta:
        verbose_name = _("Material Category")
        verbose_name_plural = _("Material Categories")
        ordering = ['name']

    def __str__(self):
        return self.name


class Material(TimeStampModel):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(MaterialCategory, on_delete=models.PROTECT, related_name='materials')
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='materials')
    description = models.TextField(blank=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=0.000)
    is_active = models.BooleanField(default=True)
    expire_date = models.TextField(blank=True, null=True)
    spec_key1 = models.CharField(max_length=100, blank=True, null=True)
    spec_key2 = models.CharField(max_length=100, blank=True, null=True)
    spec_key3 = models.CharField(max_length=100, blank=True, null=True)
    spec_key4 = models.CharField(max_length=100, blank=True, null=True)
    spec_key5 = models.CharField(max_length=100, blank=True, null=True)
    spec_val1 = models.CharField(max_length=100, blank=True, null=True)
    spec_val2 = models.CharField(max_length=100, blank=True, null=True)
    spec_val3 = models.CharField(max_length=100, blank=True, null=True)
    spec_val4 = models.CharField(max_length=100, blank=True, null=True)
    spec_val5 = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = _("Material")
        verbose_name_plural = _("Materials")
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class Warehouse(TimeStampModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Warehouse")
        verbose_name_plural = _("Warehouses")
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


# ==========================================
# 2. Accounting: Chart of Accounts & General Ledger
# ==========================================

class Account(TimeStampModel):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    parent = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='children'
    )
    balance = models.DecimalField(default=0.00, max_digits=14, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class JournalEntry(TimeStampModel):
    entry_number = models.CharField(max_length=100, unique=True)
    entry_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    description = models.TextField(blank=True)
    
    # Origin document tracking
    origin_type = models.CharField(max_length=50, blank=True, null=True)
    origin_id = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        verbose_name = _("Journal Entry")
        verbose_name_plural = _("Journal Entries")
        ordering = ['-entry_date', '-entry_number']

    def __str__(self):
        return f"JV #{self.entry_number} ({self.entry_date})"


class JournalEntryLine(TimeStampModel):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0.00)
    memo = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = _("Journal Entry Line")
        verbose_name_plural = _("Journal Entry Lines")

    def clean(self):
        if self.debit > 0 and self.credit > 0:
            raise ValidationError(_("A single line cannot have both a debit and a credit amount."))
        if self.debit == 0 and self.credit == 0:
            raise ValidationError(_("A line must have either a debit or a credit amount."))

    def __str__(self):
        return f"{self.account.name}: Dr {self.debit} / Cr {self.credit}"


# ==========================================
# 3. Commercial: Partners, Invoices & Payments
# ==========================================

class Client(TimeStampModel):
    name = models.CharField(max_length=150)
    client_type = models.CharField(max_length=20, choices=[('customer', 'Customer'), ('supplier', 'Supplier')], default='customer')
    tax_number = models.CharField(max_length=50, blank=True) ## may need its own table 
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Client")
        verbose_name_plural = _("Clients")
        ordering = ['name']

    def __str__(self):
        return self.name


class InvoiceType(TimeStampModel):
    name = models.CharField(max_length=100)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    affects_inventory = models.BooleanField(default=True)
    affects_accounting = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Invoice Type")
        verbose_name_plural = _("Invoice Types")
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.direction})"


class Invoice(TimeStampModel):
    invoice_type = models.ForeignKey(InvoiceType, on_delete=models.PROTECT, related_name='invoices')
    invoice_number = models.CharField(max_length=100, unique=True)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    partner = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='invoices')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='invoices', null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    # Financial summaries
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")
        ordering = ['-invoice_date', '-invoice_number']

    def __str__(self):
        return f"[{self.invoice_number}] {self.partner.name} - {self.total_amount}"


class InvoiceMaterial(TimeStampModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='invoice_items')
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, null=True, blank=True,
        help_text="Optional line-level override for warehouse fulfillment"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        verbose_name = _("Invoice Item")
        verbose_name_plural = _("Invoice Items")

    def __str__(self):
        return f"{self.material.code} x {self.quantity} ({self.line_total})"


class Payment(TimeStampModel):
    payment_number = models.CharField(max_length=100, unique=True)
    payment_date = models.DateField()
    partner = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, null=True, blank=True, related_name='payments')
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='payments')
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ['-payment_date', '-payment_number']

    def __str__(self):
        return f"Payment {self.payment_number}: {self.amount} ({self.partner.name})"


# ==========================================
# 4. Inventory: Balances & Movement Ledger
# ==========================================

class WarehouseStock(TimeStampModel):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='stock_levels')
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='stock_levels')
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0.000)

    class Meta:
        unique_together = ('warehouse', 'material')
        verbose_name = _("Warehouse Stock")
        verbose_name_plural = _("Warehouse Stock Levels")

    def __str__(self):
        return f"{self.warehouse.code} - {self.material.code}: {self.quantity}"


class StockMovement(TimeStampModel):
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='stock_movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='stock_movements')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    reference_number = models.CharField(max_length=100, blank=True)
    invoice_line = models.ForeignKey(InvoiceMaterial, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Stock Movement")
        verbose_name_plural = _("Stock Movements")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.movement_type} - {self.material.code} ({self.quantity}) at {self.warehouse.code}"


# ==========================================
# 5. System Configuration
# ==========================================

class Setting(TimeStampModel):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Setting")
        verbose_name_plural = _("Settings")
        ordering = ['key']

    def __str__(self):
        return self.key
