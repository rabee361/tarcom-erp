import json
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from tarcom.base.forms import *
from tarcom.base.models import *
from tarcom.utils.enums import FeatureReason, OrderStatus, UserType

from .auth import ProtectedDeleteMixin, StaffRequiredMixin


class DashboardView(StaffRequiredMixin, View):
    def get(self, request):
        context = {}
        return render(request, "dashboard/dashboard.html", context=context)


class DashboardPartialView(StaffRequiredMixin, View):
    def get(self, request):
        context = {
            "products_count": Material.objects.count(),
            "categories_count": MaterialCategory.objects.count(),
            "orders_count": Order.objects.filter(status=OrderStatus.PENDING).count(),
            "clients_count": CustomUser.objects.filter(
                user_type=UserType.CUSTOMER
            ).count(),
            "admins_count": CustomUser.objects.filter(is_staff=True).count(),
            "total_sales": Order.objects.exclude(
                status=OrderStatus.CANCELLED
            ).aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00"),
        }
        return render(
            request, "dashboard/partials/dashboard_partial.html", context=context
        )


class MaterialListView(StaffRequiredMixin, ListView):
    model = Material
    template_name = "dashboard/materials/materials_list.html"
    context_object_name = "materials"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            Material.objects.select_related("category", "uom")
            .all()
            .order_by("-created_at")
        )
        q = self.request.GET.get("q")
        cat_id = self.request.GET.get("category")
        if self.request.htmx:
            self.template_name = "dashboard/partials/materials_partial.html"
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(name_en__icontains=q) | Q(name_ar__icontains=q)
            )
        if cat_id:
            qs = qs.filter(category_id=cat_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categories"] = MaterialCategory.objects.all()
        return ctx


class MaterialCreateView(StaffRequiredMixin, CreateView):
    model = Material
    form_class = MaterialForm
    template_name = "dashboard/materials/material_form.html"
    success_url = reverse_lazy("materials-list")

    def form_valid(self, form):
        messages.success(self.request, "تم إضافة المادة بنجاح.")
        return super().form_valid(form)


class MaterialUpdateView(StaffRequiredMixin, UpdateView):
    model = Material
    form_class = MaterialForm
    template_name = "dashboard/materials/material_form.html"
    success_url = reverse_lazy("materials-list")

    def form_valid(self, form):
        messages.success(self.request, "تم تعديل المادة بنجاح.")
        return super().form_valid(form)


class MaterialDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = Material
    http_method_names = ["post"]
    success_url = reverse_lazy("materials-list")
    protected_message = "لا يمكن حذف المادة لارتباطها بطلبات أو حركات أخرى في النظام."
    deleted_message = "تم حذف المادة بنجاح."


MAX_FEATURED_MATERIALS = 10


class MaterialFeaturesView(StaffRequiredMixin, View):
    template_name = "dashboard/materials/material_features.html"
    rows_template = "dashboard/partials/features_partial.html"

    def get_materials(self, request):
        qs = (
            Material.objects.select_related("category", "uom")
            .all()
            .order_by("-created_at")
        )
        q = request.GET.get("q")
        cat_id = request.GET.get("category")
        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(name_en__icontains=q) | Q(name_ar__icontains=q)
            )
        if cat_id:
            qs = qs.filter(category_id=cat_id)
        return qs

    def build_context(self, materials, state=None):
        rows = []
        for material in materials:
            if state is not None and material.pk in state:
                checked, reason = state[material.pk]
            else:
                checked, reason = material.is_feature, material.feature_reason
            rows.append({"material": material, "checked": checked, "reason": reason})
        return {
            "rows": rows,
            "categories": MaterialCategory.objects.all(),
            "reasons": FeatureReason.choices,
            "max_features": MAX_FEATURED_MATERIALS,
            "featured_count": sum(row["checked"] for row in rows),
        }

    def get(self, request):
        materials = self.get_materials(request)
        return render(request, self.template_name, self.build_context(materials))

    def htmx_response(self, request, materials, state, alerts):
        context = self.build_context(materials, state=state)
        response = render(request, self.rows_template, context)
        response["HX-Trigger"] = json.dumps({"featuresMessage": alerts})
        return response

    def post(self, request):
        materials = list(self.get_materials(request))
        state = {
            material.pk: (
                request.POST.get(f"feature_{material.pk}") is not None,
                request.POST.get(f"reason_{material.pk}", ""),
            )
            for material in materials
        }

        errors = []
        checked_ids = {pk for pk, (checked, _) in state.items() if checked}
        untouched_featured = (
            Material.objects.filter(is_feature=True).exclude(pk__in=state).count()
        )
        if len(checked_ids) + untouched_featured > MAX_FEATURED_MATERIALS:
            errors.append(f"لا يمكن تمييز أكثر من {MAX_FEATURED_MATERIALS} مواد.")
        missing_reasons = [
            str(material.name)
            for material in materials
            if state[material.pk][0]
            and state[material.pk][1] not in FeatureReason.values
        ]
        if missing_reasons:
            errors.append("يرجى تحديد سبب التمييز للمواد: " + "، ".join(missing_reasons))

        if errors:
            if request.htmx:
                return self.htmx_response(request, materials, state, errors)
            for error in errors:
                messages.error(request, error)
            context = self.build_context(materials, state=state)
            return render(request, self.template_name, context)

        now = timezone.now()
        for material in materials:
            checked, reason = state[material.pk]
            material.is_feature = checked
            material.feature_reason = reason if checked else ""
            material.updated_at = now
        if materials:
            with transaction.atomic():
                Material.objects.bulk_update(
                    materials, ["is_feature", "feature_reason", "updated_at"]
                )
        if request.htmx:
            return self.htmx_response(
                request,
                self.get_materials(request),
                None,
                ["تم تحديث المواد المميزة بنجاح."],
            )
        messages.success(request, "تم تحديث المواد المميزة بنجاح.")
        return redirect("materials-features")


class CategoryListView(StaffRequiredMixin, ListView):
    model = MaterialCategory
    template_name = "dashboard/categories/categories_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        qs = MaterialCategory.objects.all().order_by("name")
        if self.request.htmx:
            self.template_name = "dashboard/partials/categories_partial.html"
        if self.request.GET.get("q"):
            q = self.request.GET.get("q")
            qs = qs.filter(
                Q(name__icontains=q) | Q(name_en__icontains=q) | Q(name_ar__icontains=q)
            )
        return qs


class CategoryCreateView(StaffRequiredMixin, CreateView):
    model = MaterialCategory
    form_class = CategoryForm
    template_name = "dashboard/categories/category_form.html"
    success_url = reverse_lazy("categories-list")

    def form_valid(self, form):
        messages.success(self.request, "تم إضافة التصنيف بنجاح.")
        return super().form_valid(form)


class CategoryUpdateView(StaffRequiredMixin, UpdateView):
    model = MaterialCategory
    form_class = CategoryForm
    template_name = "dashboard/categories/category_form.html"
    success_url = reverse_lazy("categories-list")

    def form_valid(self, form):
        messages.success(self.request, "تم تعديل التصنيف بنجاح.")
        return super().form_valid(form)


class CategoryDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = MaterialCategory
    http_method_names = ["post"]
    success_url = reverse_lazy("categories-list")
    protected_message = "لا يمكن حذف التصنيف لارتباطه بمنتجات في النظام."
    deleted_message = "تم حذف التصنيف بنجاح."


class UnitListView(StaffRequiredMixin, ListView):
    model = UnitOfMeasure
    template_name = "dashboard/units/units_list.html"
    context_object_name = "units"

    def get_queryset(self):
        qs = UnitOfMeasure.objects.all().order_by("name")
        if self.request.htmx:
            self.template_name = "dashboard/partials/uom_partial.html"
        if self.request.GET.get("q"):
            q = self.request.GET.get("q")
            qs = qs.filter(
                Q(name__icontains=q) | Q(name_en__icontains=q) | Q(name_ar__icontains=q)
            )
        return qs


class UnitCreateView(StaffRequiredMixin, CreateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "dashboard/units/unit_form.html"
    success_url = reverse_lazy("units-list")

    def form_valid(self, form):
        messages.success(self.request, "تم إضافة وحدة القياس بنجاح.")
        return super().form_valid(form)


class UnitUpdateView(StaffRequiredMixin, UpdateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "dashboard/units/unit_form.html"
    success_url = reverse_lazy("units-list")

    def form_valid(self, form):
        messages.success(self.request, "تم تعديل وحدة القياس بنجاح.")
        return super().form_valid(form)


class UnitDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = UnitOfMeasure
    http_method_names = ["post"]
    success_url = reverse_lazy("units-list")
    protected_message = "لا يمكن حذف وحدة القياس لارتباطها بمنتجات في النظام."
    deleted_message = "تم حذف وحدة القياس بنجاح."


class OrderListView(StaffRequiredMixin, ListView):
    model = Order
    template_name = "dashboard/orders/orders_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.select_related("user").all().order_by("-created_at")
        status_param = self.request.GET.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q)
                | Q(user__email__icontains=q)
                | Q(shipping_phone__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = OrderStatus.choices
        return ctx


class OrderDetailView(StaffRequiredMixin, DetailView):
    model = Order
    template_name = "dashboard/orders/order_detail.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_form"] = OrderDashboardStatusForm(
            initial={
                "status": self.object.status,
                "payment_status": self.object.payment_status,
            }
        )
        return ctx


class OrderStatusUpdateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderDashboardStatusForm(request.POST)
        if form.is_valid():
            order.status = form.cleaned_data["status"]
            order.payment_status = form.cleaned_data["payment_status"]
            order.save(update_fields=["status", "payment_status"])
            messages.success(
                request, f"تم تحديث حالة الطلب #{order.order_number} بنجاح."
            )
        else:
            messages.error(request, "تعذر تحديث حالة الطلب. الرجاء اختيار قيم صحيحة.")
        return redirect("order-detail", pk=order.pk)
