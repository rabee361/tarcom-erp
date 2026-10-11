from decimal import Decimal

from django.test import TestCase

from tarcom.base.models import (
    CustomUser,
    Material,
    MaterialCategory,
    UnitOfMeasure,
)
from tarcom.utils.enums import UserType


class DashboardProtectedDeleteTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
            user_type=UserType.ADMIN,
        )
        self.client.force_login(self.staff)
        self.uom = UnitOfMeasure.objects.create(name="Piece", code="PCS")
        self.category = MaterialCategory.objects.create(name="Steel")
        self.material = Material.objects.create(
            name="Steel Rod",
            category=self.category,
            uom=self.uom,
            consumer_price=Decimal("100.00"),
        )

    def test_protected_records_redirect_with_message_instead_of_500(self):
        # Category and unit are protected by the material that uses them
        for url, pk, model in [
            (
                f"/dashboard/categories/{self.category.pk}/delete/",
                self.category.pk,
                MaterialCategory,
            ),
            (f"/dashboard/units/{self.uom.pk}/delete/", self.uom.pk, UnitOfMeasure),
        ]:
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(model.objects.filter(pk=pk).exists())
            # The flash message rendered on the list page explains why
            followed = self.client.get(response["Location"])
            self.assertEqual(followed.status_code, 200)
            self.assertContains(followed, "لا يمكن حذف")

    def test_ajax_delete_returns_json_and_deletes(self):
        url = f"/dashboard/materials/{self.material.pk}/delete/"
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "تم حذف المادة بنجاح.")
        self.assertFalse(Material.objects.filter(pk=self.material.pk).exists())

    def test_ajax_delete_of_protected_record_returns_error_json(self):
        url = f"/dashboard/categories/{self.category.pk}/delete/"
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["message"].startswith("لا يمكن حذف"))
        self.assertTrue(MaterialCategory.objects.filter(pk=self.category.pk).exists())

    def test_ajax_delete_of_own_account_returns_error_json(self):
        url = f"/dashboard/users/{self.staff.pk}/delete/"
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertTrue(CustomUser.objects.filter(pk=self.staff.pk).exists())
