from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.core.cache import cache
from django.db.models import Q
from django.shortcuts import render, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from tarcom.utils.mixins import ProtectedDeleteMixin, StaffRequiredMixin
from tarcom.utils.helper import get_client_ip

from tarcom.base.forms import *
from tarcom.base.models import CustomUser



class DashboardLoginView(View):
    template_name = "dashboard/login.html"
    max_attempts = 3
    lockout_duration = 900  # 15 minutes

    def get(self, request):
        if request.user.is_authenticated and (request.user.is_staff or getattr(request.user, 'is_admin', False)):
            return redirect('dashboard')
        form = DashboardLoginForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = DashboardLoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        identifier = form.cleaned_data['phonenumber'].strip()
        password = form.cleaned_data['password']
        remember_me = form.cleaned_data.get('remember_me')
        cache_key = f"dashboard_login_attempts_{get_client_ip(request)}_{identifier.lower()}"

        attempts = cache.get(cache_key, 0)
        if attempts >= self.max_attempts:
            messages.error(
                request,
                "لقد تم حظر المحاولات مؤقتاً بسبب تجاوز 3 محاولات خاطئة. يرجى المحاولة بعد 15 دقيقة."
            )
            return render(request, self.template_name, {'form': form, 'locked': True})

        user_obj = CustomUser.objects.filter(
            Q(email__iexact=identifier) | Q(phone=identifier)
        ).first()

        user = None
        if user_obj:
            user = authenticate(request, username=user_obj.email, password=password)

        if user is None:
            new_attempts = attempts + 1
            cache.set(cache_key, new_attempts, self.lockout_duration)
            remaining = self.max_attempts - new_attempts
            if remaining > 0:
                messages.error(request, f"بيانات الدخول غير صحيحة. متبقي لديك {remaining} محاولة.")
            else:
                messages.error(request, "تم استنفاد جميع المحاولات (3). تم قفل الحساب مؤقتاً لمدة 15 دقيقة.")
            return render(request, self.template_name, {'form': form})

        if not (user.is_staff or getattr(user, 'is_admin', False)):
            messages.error(request, "عذراً، هذا الحساب ليس لديه صلاحية الدخول إلى لوحة التحكم.")
            return render(request, self.template_name, {'form': form})

        cache.delete(cache_key)
        login(request, user)
        if remember_me:
            request.session.set_expiry(1209600)  # 2 weeks
        else:
            request.session.set_expiry(0)  # Expires on browser close

        next_url = request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect('dashboard')


class DashboardLogoutView(View):
    def post(self, request):
        logout(request)
        return redirect('login')


class DashboardChangePasswordView(StaffRequiredMixin, View):
    template_name = "dashboard/users/change_password.html"

    def get(self, request):
        form = DashboardChangePasswordForm(user=request.user)
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = DashboardChangePasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تغيير كلمة المرور بنجاح. يرجى تسجيل الدخول مجدداً.")
            return redirect('login')
        return render(request, self.template_name, {'form': form})


class UsersListView(StaffRequiredMixin, ListView):
    model = CustomUser
    template_name = "dashboard/users/users_list.html"
    context_object_name = "users"
    paginate_by = 20

    def get_queryset(self):
        qs = CustomUser.objects.all().order_by('-date_joined')
        user_type = self.request.GET.get('user_type')
        if user_type:
            qs = qs.filter(user_type=user_type)
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone__icontains=q)
            )
        return qs


class UserCreateView(StaffRequiredMixin, CreateView):
    model = CustomUser
    form_class = UserForm
    template_name = "dashboard/users/user_form.html"
    success_url = reverse_lazy('users-list')

    def form_valid(self, form):
        messages.success(self.request, "تم إنشاء المستخدم بنجاح.")
        return super().form_valid(form)


class UserUpdateView(StaffRequiredMixin, UpdateView):
    model = CustomUser
    form_class = UserForm
    template_name = "dashboard/users/user_form.html"
    success_url = reverse_lazy('users-list')

    def form_valid(self, form):
        messages.success(self.request, "تم تحديث بيانات المستخدم بنجاح.")
        return super().form_valid(form)


class UserDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = CustomUser
    template_name = "dashboard/users/user_confirm_delete.html"
    success_url = reverse_lazy('users-list')
    protected_message = "لا يمكن حذف هذا المستخدم لارتباطه بطلبات أو بيانات أخرى في النظام."
    deleted_message = "تم حذف المستخدم بنجاح."

    def form_valid(self, form):
        # DeleteView posts to a plain Form, the object lives on self.object
        if self.object == self.request.user:
            messages.error(self.request, "لا يمكنك حذف حسابك الحالي أثناء تسجيل الدخول.")
            return redirect(self.success_url)
        return super().form_valid(form)
