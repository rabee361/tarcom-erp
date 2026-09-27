from django.views import View
from django.shortcuts import render

from .models import CustomUser, Material, MaterialCategory


class DashboardView(View):
    def get(self, request):
        context = {}
        return render(request, "dashboard.html", context=context)


class DashboardPartialView(View):
    """
    Stats-grid fragment loaded by htmx into #dashboard-partial on /dashboard/.
    Counts for models that do not exist yet (orders, clients, warehouses,
    invoices, suppliers) are omitted so the template's |default:"0" applies.
    """

    def get(self, request):
        context = {
            "products_count": Material.objects.count(),
            "categories_count": MaterialCategory.objects.count(),
            "admins_count": CustomUser.objects.filter(is_staff=True).count(),
        }
        return render(request, "partials/dashboard_partial.html", context=context)