from django.db import models
from django.utils.translation import gettext_lazy as _


class MovementType(models.TextChoices):
    IN = 'IN', _('Stock In (Purchase/Return)')
    OUT = 'OUT', _('Stock Out (Sale/Disposal)')
    TRANSFER = 'TRANSFER', _('Internal Transfer')
    ADJUSTMENT = 'ADJUSTMENT', _('Physical Count Adjustment')

class PaymentMethod(models.TextChoices):
    CASH = 'CASH', _('Cash')
    BANK_TRANSFER = 'BANK_TRANSFER', _('Bank Transfer')
    CHECK = 'CHECK', _('Check')
    CARD = 'CARD', _('Credit/Debit Card')

class AccountType(models.TextChoices):
    ASSET = 'ASSET', _('Asset')
    LIABILITY = 'LIABILITY', _('Liability')
    EQUITY = 'EQUITY', _('Equity')
    REVENUE = 'REVENUE', _('Revenue')
    EXPENSE = 'EXPENSE', _('Expense')

class Status(models.TextChoices):
    DRAFT = 'DRAFT', _('Draft')
    POSTED = 'POSTED', _('Posted / Confirmed')
    PAID = 'PAID', _('Paid')
    CANCELLED = 'CANCELLED', _('Cancelled')

class Direction(models.TextChoices):
    SALE = 'SALE', _('Sales Invoice')
    PURCHASE = 'PURCHASE', _('Purchase Bill')
    CUSTOMER_RETURN = 'CUSTOMER_RETURN', _('Customer Return')
    SUPPLIER_RETURN = 'SUPPLIER_RETURN', _('Supplier Return')
    PROFORMA = 'PROFORMA', _('Proforma Invoice')

class CodeTypes(models.TextChoices):
    SIGNUP = 'SIGNUP'
    RESET_PASSWORD = 'RESET_PASSWORD'
    FORGET_PASSWORD = 'FORGET_PASSWORD'

class UserType(models.TextChoices):
    BUYER = 'buyer', 'Buyer'
    SELLER = 'seller', 'Seller'
    ADMIN = 'admin', 'Admin'
