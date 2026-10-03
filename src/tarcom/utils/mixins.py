from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy


class ProtectedDeleteMixin:
    """
    Turns ProtectedError (record referenced by other rows, e.g. a material used
    in an order) into a user-facing message instead of a server error, and
    confirms a successful delete with `deleted_message`.

    Requests sent by the delete modal (X-Requested-With: XMLHttpRequest) get a
    JSON response `{ok, message}` so the page can stay put; everything else
    gets the classic flash message + redirect.
    """
    protected_message = "لا يمكن حذف هذا العنصر لارتباطه ببيانات أخرى في النظام."
    deleted_message = None

    def is_ajax_request(self):
        return self.request.headers.get("x-requested-with") == "XMLHttpRequest"

    def form_valid(self, form):
        target_pk = self.object.pk
        try:
            response = super().form_valid(form)
        except ProtectedError:
            if self.is_ajax_request():
                return JsonResponse({"ok": False, "message": self.protected_message})
            messages.error(self.request, self.protected_message)
            return redirect(self.success_url)

        if self.deleted_message and not self.model.objects.filter(pk=target_pk).exists():
            if self.is_ajax_request():
                return JsonResponse({"ok": True, "message": self.deleted_message})
            messages.success(self.request, self.deleted_message)
        return response


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy('login')

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_staff or getattr(user, 'is_admin', False))

    def handle_no_permission(self):
        # Authenticated non-staff users are sent to the login page instead of a 403.
        if self.request.user.is_authenticated:
            return redirect_to_login(self.request.get_full_path(), self.login_url)
        return super().handle_no_permission()
