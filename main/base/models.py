from django.db import models
 

class TimeStampModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class MaterialCategory(TimeStampModel):
    name = models.CharField(max_length=100) 

class Material(TimeStampModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=255)
    category = models.ForeignKey(MaterialCategory, on_delete=models.CASCADE)
 
class Warehouse(TimeStampModel):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=255)

class WarehouseMaterial(TimeStampModel):
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    invoice_item = models.ForeignKey('InvoiceMaterial', on_delete=models.CASCADE, null=True, blank=True)

class InvoiceType(TimeStampModel):
    name = models.CharField(max_length=100)

class Client(TimeStampModel):
    client_type = models.CharField(choices=[('customer', 'Customer'), ('supplier', 'Supplier')], max_length=20)
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()

class Invoice(TimeStampModel):
    invoice_type = models.ForeignKey(InvoiceType, on_delete=models.CASCADE)
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    client = models.ForeignKey(Client, on_delete=models.CASCADE)

class InvoiceMaterial(TimeStampModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity = models.IntegerField()

class Account(TimeStampModel):
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20)
    balance = models.DecimalField(default=0.0, max_digits=10, decimal_places=2)

class JournalEntry(TimeStampModel):
    entry_date = models.DateField()
    origin_type = models.CharField(max_length=100, null=True, blank=True)

class JournalEntrItem(TimeStampModel):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE)
    debit_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='debit_entries')
    credit_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='credit_entries')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField()

class Setting(TimeStampModel):
    key = models.CharField(max_length=100)
    value = models.CharField(max_length=100)
