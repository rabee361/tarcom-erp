from django.test import TestCase

from tarcom.base.models import CustomUser, Order
from tarcom.utils.enums import UserType


class DashboardUsersCrudTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
            user_type=UserType.ADMIN,
        )
        self.client.force_login(self.staff)

    def _payload(self, email, **extra):
        data = {
            "email": email,
            "first_name": "First",
            "last_name": "User",
            "phone": "+963912345678",
            # `admins-list` is the admins page, so the CRUD flow is exercised
            # with admins to keep the list assertion below meaningful.
            "user_type": UserType.ADMIN,
            "is_active": "on",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }
        data.update(extra)
        return data

    def test_dashboard_users_crud(self):
        # Two consecutive creates prove the username collision is handled
        response = self.client.post(
            "/dashboard/admins/create/", self._payload("first@example.com")
        )
        self.assertRedirects(response, "/dashboard/admins/")
        response = self.client.post(
            "/dashboard/admins/create/", self._payload("second@example.com")
        )
        self.assertRedirects(response, "/dashboard/admins/")

        first = CustomUser.objects.get(email="first@example.com")
        self.assertTrue(first.check_password("StrongPass123!"))
        self.assertEqual(first.username, "first@example.com")

        # List
        response = self.client.get("/dashboard/admins/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "first@example.com")

        # Edit (password untouched when left blank)
        edit = self._payload(
            "first@example.com", password="", confirm_password="", first_name="Edited"
        )
        response = self.client.post(f"/dashboard/admins/{first.pk}/edit/", edit)
        self.assertRedirects(response, "/dashboard/admins/")
        first.refresh_from_db()
        self.assertEqual(first.first_name, "Edited")
        self.assertTrue(first.check_password("StrongPass123!"))

        # Delete
        response = self.client.post(f"/dashboard/admins/{first.pk}/delete/")
        self.assertRedirects(response, "/dashboard/admins/")
        self.assertFalse(CustomUser.objects.filter(pk=first.pk).exists())

    def test_dashboard_user_cannot_delete_own_account(self):
        response = self.client.post(f"/dashboard/admins/{self.staff.pk}/delete/")
        self.assertRedirects(response, "/dashboard/admins/")
        self.assertTrue(CustomUser.objects.filter(pk=self.staff.pk).exists())


class DashboardUserPagesTest(TestCase):
    """Admins, customers and suppliers each live on their own page."""

    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
            user_type=UserType.ADMIN,
        )
        self.customer = CustomUser.objects.create_user(
            email="cust@tarcom.com",
            password="CustPass123!",
            user_type=UserType.CUSTOMER,
        )
        self.supplier = CustomUser.objects.create_user(
            email="sup@tarcom.com",
            password="SupPass123!",
            user_type=UserType.SUPPLIER,
        )
        self.other_admin = CustomUser.objects.create_user(
            email="second-admin@tarcom.com",
            password="AdminPass123!",
            user_type=UserType.ADMIN,
        )
        self.client.force_login(self.staff)

    def test_users_list_shows_only_admins(self):
        response = self.client.get("/dashboard/admins/")
        self.assertEqual(response.status_code, 200)
        # Assert on the list, not the rendered HTML: the sidebar prints the
        # signed-in user's email on every page.
        self.assertEqual(
            {u.email for u in response.context["admins"]},
            {self.staff.email, "second-admin@tarcom.com"},
        )

    def test_customers_list_shows_only_customers(self):
        response = self.client.get("/dashboard/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {u.email for u in response.context["customers"]}, {self.customer.email}
        )
        self.assertNotContains(response, "sup@tarcom.com")

    def test_suppliers_list_shows_only_suppliers(self):
        response = self.client.get("/dashboard/suppliers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {u.email for u in response.context["suppliers"]}, {self.supplier.email}
        )
        self.assertNotContains(response, "cust@tarcom.com")

    def test_lists_are_searchable(self):
        response = self.client.get("/dashboard/customers/", {"q": "sup@tarcom"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "cust@tarcom.com")

    def test_customer_create_presets_user_type(self):
        payload = {
            "email": "new-cust@tarcom.com",
            "first_name": "New",
            "last_name": "Customer",
            "phone": "+963912345678",
            "user_type": UserType.CUSTOMER,
            "is_active": "on",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }
        response = self.client.post("/dashboard/customers/create/", payload)
        self.assertRedirects(response, "/dashboard/customers/")
        created = CustomUser.objects.get(email="new-cust@tarcom.com")
        self.assertEqual(created.user_type, UserType.CUSTOMER)
        self.assertTrue(created.check_password("StrongPass123!"))

    def test_supplier_create_presets_user_type(self):
        payload = {
            "email": "new-sup@tarcom.com",
            "first_name": "New",
            "last_name": "Supplier",
            "phone": "+963912345678",
            "user_type": UserType.SUPPLIER,
            "is_active": "on",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }
        response = self.client.post("/dashboard/suppliers/create/", payload)
        self.assertRedirects(response, "/dashboard/suppliers/")
        created = CustomUser.objects.get(email="new-sup@tarcom.com")
        self.assertEqual(created.user_type, UserType.SUPPLIER)

    def test_customer_form_hides_the_user_type_dropdown(self):
        response = self.client.get("/dashboard/customers/create/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="hidden"')
        self.assertNotContains(response, "<select")

    def test_customer_edit_rejects_a_supplier(self):
        # The update view is scoped to customers, so a supplier is a 404.
        response = self.client.get(f"/dashboard/customers/{self.supplier.pk}/edit/")
        self.assertEqual(response.status_code, 404)

    def test_customer_delete_ajax(self):
        url = f"/dashboard/customers/{self.customer.pk}/delete/"
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "تم حذف العميل بنجاح.")
        self.assertFalse(CustomUser.objects.filter(pk=self.customer.pk).exists())

    def test_supplier_delete_ajax(self):
        url = f"/dashboard/suppliers/{self.supplier.pk}/delete/"
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "تم حذف المورد بنجاح.")
        self.assertFalse(CustomUser.objects.filter(pk=self.supplier.pk).exists())

    def test_pages_require_staff(self):
        self.client.logout()
        for url in (
            "/dashboard/customers/",
            "/dashboard/suppliers/",
            "/dashboard/admins/",
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302, url)
                self.assertIn("/login/", response["Location"])

    def test_customer_delete_url_cannot_delete_a_non_customer(self):
        # DeleteView resolves `model._default_manager.all()` unless the view
        # narrows it, which made every user deletable through the customers URL.
        for victim in (self.staff, self.other_admin, self.supplier):
            with self.subTest(email=victim.email):
                url = f"/dashboard/customers/{victim.pk}/delete/"
                response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
                self.assertEqual(response.status_code, 404, url)
                self.assertTrue(CustomUser.objects.filter(pk=victim.pk).exists())

    def test_supplier_delete_url_cannot_delete_a_non_supplier(self):
        for victim in (self.staff, self.other_admin, self.customer):
            with self.subTest(email=victim.email):
                url = f"/dashboard/suppliers/{victim.pk}/delete/"
                response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
                self.assertEqual(response.status_code, 404, url)
                self.assertTrue(CustomUser.objects.filter(pk=victim.pk).exists())

    def test_customer_create_ignores_a_tampered_user_type(self):
        # The hidden input is client-side editable, so the view must not trust it.
        payload = {
            "email": "tampered@t.com",
            "first_name": "T",
            "last_name": "T",
            "phone": "+963912345678",
            "user_type": UserType.ADMIN,
            "is_active": "on",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }
        self.client.post("/dashboard/customers/create/", payload)
        self.assertEqual(
            CustomUser.objects.get(email="tampered@t.com").user_type, UserType.CUSTOMER
        )

    def test_supplier_create_ignores_a_tampered_user_type(self):
        payload = {
            "email": "tampered-sup@t.com",
            "first_name": "T",
            "last_name": "T",
            "phone": "+963912345678",
            "user_type": UserType.ADMIN,
            "is_active": "on",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }
        self.client.post("/dashboard/suppliers/create/", payload)
        self.assertEqual(
            CustomUser.objects.get(email="tampered-sup@t.com").user_type,
            UserType.SUPPLIER,
        )

    def test_customer_edit_cannot_grant_staff_or_superuser(self):
        payload = {
            "email": self.customer.email,
            "first_name": "C",
            "last_name": "U",
            "phone": "+963912345678",
            "user_type": UserType.ADMIN,
            "is_active": "on",
            "is_staff": "on",
            "is_superuser": "on",
            "password": "",
            "confirm_password": "",
        }
        self.client.post(f"/dashboard/customers/{self.customer.pk}/edit/", payload)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.user_type, UserType.CUSTOMER)
        self.assertFalse(self.customer.is_staff)
        self.assertFalse(self.customer.is_superuser)

    def test_delete_is_refused_for_a_customer_with_orders(self):
        ordered = CustomUser.objects.create_user(
            email="ordered@t.com",
            password="StrongPass123!",
            user_type=UserType.CUSTOMER,
        )
        Order.objects.create(user=ordered)
        url = f"/dashboard/customers/{ordered.pk}/delete/"
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["message"].startswith("لا يمكن حذف"))
        self.assertTrue(CustomUser.objects.filter(pk=ordered.pk).exists())
