from django.contrib import admin
from .models import *


admin.site.register(MaterialCategory)
admin.site.register(Material)
admin.site.register(Warehouse)
admin.site.register(WarehouseMaterial)
admin.site.register(Invoice)
admin.site.register(InvoiceMaterial)