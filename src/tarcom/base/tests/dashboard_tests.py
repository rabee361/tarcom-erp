from decimal import Decimal

from django.test import TestCase

from tarcom.base.models import (
    CustomUser,
    Material,
    MaterialCategory,
    Order,
    UnitOfMeasure,
)
from tarcom.utils.enums import UserType


class DashboardViewTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )

    def test_dashboard_redirects_anonymous_user_to_login(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].startswith("/login/"), response["Location"]
        )

    def test_dashboard_renders_for_staff_user(self):
        # base.html sidebar profile block must not crash on a signed-in staff user
        self.client.force_login(self.staff)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('hx-get="/dashboard/partial/"', response.content.decode())

    def test_dashboard_partial_returns_stat_cards(self):
        self.client.force_login(self.staff)
        response = self.client.get("/dashboard/partial/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # 8 stat cards, with context variables resolved (no leftover {{ ... }})
        self.assertEqual(body.count("stat-card"), 8)
        self.assertNotIn("_count", body)


class DashboardPageRenderTest(TestCase):
    """Every dashboard route must render (or redirect) without a server error."""

    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.customer = CustomUser.objects.create_user(
            email="customer@tarcom.com",
            password="CustomerPass123!",
            user_type=UserType.ADMIN,
        )
        self.uom = UnitOfMeasure.objects.create(name="Piece", code="PCS")
        self.category = MaterialCategory.objects.create(name="Steel")
        self.material = Material.objects.create(
            name="Steel Rod",
            category=self.category,
            uom=self.uom,
            consumer_price=Decimal("100.00"),
        )
        self.order = Order.objects.create(user=self.customer)
        self.client.force_login(self.staff)

    def test_dashboard_pages_render(self):
        pages = [
            "/",
            "/dashboard/",
            "/dashboard/users/",
            "/dashboard/users/create/",
            f"/dashboard/users/{self.customer.pk}/edit/",
            "/dashboard/materials/",
            "/dashboard/materials/create/",
            f"/dashboard/materials/{self.material.pk}/edit/",
            "/dashboard/categories/",
            "/dashboard/categories/create/",
            f"/dashboard/categories/{self.category.pk}/edit/",
            "/dashboard/units/",
            "/dashboard/units/create/",
            f"/dashboard/units/{self.uom.pk}/edit/",
            "/dashboard/orders/",
            f"/dashboard/orders/{self.order.pk}/",
            "/change-password/",
        ]
        for url in pages:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_delete_pages_reject_get(self):
        urls = [
            f"/dashboard/users/{self.customer.pk}/delete/",
            f"/dashboard/materials/{self.material.pk}/delete/",
            f"/dashboard/categories/{self.category.pk}/delete/",
            f"/dashboard/units/{self.uom.pk}/delete/",
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 405, url)

    def test_login_page_renders_for_anonymous_visitor(self):
        self.client.logout()
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "login-form")

    def test_logout_ends_the_session(self):
        response = self.client.post("/logout/")
        self.assertRedirects(response, "/login/")
        self.assertIsNone(self.client.session.get("_auth_user_id"))
