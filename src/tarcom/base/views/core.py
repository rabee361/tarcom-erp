from decimal import Decimal
from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from tarcom.base.forms import *
from tarcom.base.models import *
from tarcom.utils.enums import OrderStatus, UserType
from .auth import StaffRequiredMixin, ProtectedDeleteMixin


class DashboardView(StaffRequiredMixin, View):
    def get(self, request):
        context = {}
        return render(request, "dashboard.html", context=context)


class DashboardPartialView(StaffRequiredMixin, View):
    def get(self, request):
        context = {
            "products_count": Material.objects.count(),
            "categories_count": MaterialCategory.objects.count(),
            "orders_count": Order.objects.filter(status=OrderStatus.PENDING).count(),
            "clients_count": CustomUser.objects.filter(user_type=UserType.BUYER).count(),
            "admins_count": CustomUser.objects.filter(is_staff=True).count(),
            "total_sales": Order.objects.exclude(status=OrderStatus.CANCELLED)
            .aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00'),
        }
        return render(request, "partials/dashboard_partial.html", context=context)


class MaterialListView(StaffRequiredMixin, ListView):
    model = Material
    template_name = "materials/materials_list.html"
    context_object_name = "materials"
    paginate_by = 20

    def get_queryset(self):
        qs = Material.objects.select_related('category', 'uom').all().order_by('-created_at')
        q = self.request.GET.get('q')
        cat_id = self.request.GET.get('category')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(name_en__icontains=q) | Q(name_ar__icontains=q))
        if cat_id:
            qs = qs.filter(category_id=cat_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = MaterialCategory.objects.all()
        return ctx


class MaterialCreateView(StaffRequiredMixin, CreateView):
    model = Material
    form_class = MaterialForm
    template_name = "materials/material_form.html"
    success_url = reverse_lazy('materials-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إضافة المادة بنجاح.")
        return super().form_valid(form)


class MaterialUpdateView(StaffRequiredMixin, UpdateView):
    model = Material
    form_class = MaterialForm
    template_name = "materials/material_form.html"
    success_url = reverse_lazy('materials-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تعديل المادة بنجاح.")
        return super().form_valid(form)


class MaterialDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = Material
    template_name = "materials/material_confirm_delete.html"
    success_url = reverse_lazy('materials-list')
    protected_message = "لا يمكن حذف المادة لارتباطها بطلبات أو حركات أخرى في النظام."
    deleted_message = "تم حذف المادة بنجاح."


class CategoryListView(StaffRequiredMixin, ListView):
    model = MaterialCategory
    template_name = "categories/categories_list.html"
    context_object_name = "categories"

    def get_queryset(self):
        return MaterialCategory.objects.select_related('parent').all().order_by('name')


class CategoryCreateView(StaffRequiredMixin, CreateView):
    model = MaterialCategory
    form_class = CategoryForm
    template_name = "categories/category_form.html"
    success_url = reverse_lazy('categories-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إضافة التصنيف بنجاح.")
        return super().form_valid(form)


class CategoryUpdateView(StaffRequiredMixin, UpdateView):
    model = MaterialCategory
    form_class = CategoryForm
    template_name = "categories/category_form.html"
    success_url = reverse_lazy('categories-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تعديل التصنيف بنجاح.")
        return super().form_valid(form)


class CategoryDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = MaterialCategory
    template_name = "categories/category_confirm_delete.html"
    success_url = reverse_lazy('categories-list')
    protected_message = "لا يمكن حذف التصنيف لارتباطه بمنتجات أو تصنيفات فرعية."
    deleted_message = "تم حذف التصنيف بنجاح."


class UnitListView(StaffRequiredMixin, ListView):
    model = UnitOfMeasure
    template_name = "units/units_list.html"
    context_object_name = "units"

    def get_queryset(self):
        return UnitOfMeasure.objects.all().order_by('name')


class UnitCreateView(StaffRequiredMixin, CreateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "units/unit_form.html"
    success_url = reverse_lazy('units-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إضافة وحدة القياس بنجاح.")
        return super().form_valid(form)


class UnitUpdateView(StaffRequiredMixin, UpdateView):
    model = UnitOfMeasure
    form_class = UnitOfMeasureForm
    template_name = "units/unit_form.html"
    success_url = reverse_lazy('units-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تعديل وحدة القياس بنجاح.")
        return super().form_valid(form)


class UnitDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = UnitOfMeasure
    template_name = "units/unit_confirm_delete.html"
    success_url = reverse_lazy('units-list')
    protected_message = "لا يمكن حذف وحدة القياس لارتباطها بمنتجات في النظام."
    deleted_message = "تم حذف وحدة القياس بنجاح."


class OrderListView(StaffRequiredMixin, ListView):
    model = Order
    template_name = "orders/orders_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        qs = Order.objects.select_related('user').all().order_by('-created_at')
        status_param = self.request.GET.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q)
                | Q(user__email__icontains=q)
                | Q(shipping_phone__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = OrderStatus.choices
        return ctx


class OrderDetailView(StaffRequiredMixin, DetailView):
    model = Order
    template_name = "orders/order_detail.html"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_form'] = OrderDashboardStatusForm(initial={
            'status': self.object.status,
            'payment_status': self.object.payment_status,
        })
        return ctx


class OrderStatusUpdateView(StaffRequiredMixin, View):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        form = OrderDashboardStatusForm(request.POST)
        if form.is_valid():
            order.status = form.cleaned_data['status']
            order.payment_status = form.cleaned_data['payment_status']
            order.save(update_fields=['status', 'payment_status'])
            messages.success(request, f"تم تحديث حالة الطلب #{order.order_number} بنجاح.")
        else:
            messages.error(request, "تعذر تحديث حالة الطلب. الرجاء اختيار قيم صحيحة.")
        return redirect('order-detail', pk=order.pk)
