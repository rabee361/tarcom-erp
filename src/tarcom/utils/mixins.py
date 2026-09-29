from django.db.models import ProtectedError
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse_lazy


class ProtectedDeleteMixin:
    """
    Turns ProtectedError (record referenced by other rows, e.g. a material used
    in an order) into a flash message instead of a server error, and confirms
    a successful delete with `deleted_message`.
    """
    protected_message = "لا يمكن حذف هذا العنصر لارتباطه ببيانات أخرى في النظام."
    deleted_message = None

    def form_valid(self, form):
        target_pk = self.object.pk
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, self.protected_message)
            return redirect(self.success_url)

        if self.deleted_message and not self.model.objects.filter(pk=target_pk).exists():
            messages.success(self.request, self.deleted_message)
        return response


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restricts access exclusively to staff/admin dashboard users."""
    login_url = reverse_lazy('login')

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_staff or getattr(user, 'is_admin', False))

    def handle_no_permission(self):
        # Authenticated non-staff users are sent to the login page instead of a 403.
        if self.request.user.is_authenticated:
            return redirect_to_login(self.request.get_full_path(), self.login_url)
        return super().handle_no_permission()
