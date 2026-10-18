import json
from decimal import Decimal

from django.test import TestCase

from tarcom.base.models import (
    Banner,
    Company,
    CustomUser,
    Material,
    MaterialCategory,
    Order,
    OrderItem,
    UnitOfMeasure,
)
from tarcom.utils.enums import UserType


class BulkActionTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
            user_type=UserType.ADMIN,
        )
        self.customer = CustomUser.objects.create_user(
            email="customer@tarcom.com",
            password="CustomerPass123!",
            user_type=UserType.CUSTOMER,
        )
        self.uom = UnitOfMeasure.objects.create(name="Piece", code="PCS")
        self.category = MaterialCategory.objects.create(name="Steel")
        self.company = Company.objects.create(name="Steel Co")
        self.material = Material.objects.create(
            name="Steel Rod",
            category=self.category,
            uom=self.uom,
            company=self.company,
            consumer_price=Decimal("100.00"),
        )
        self.client.force_login(self.staff)

    def _post(self, url, selected_ids, action):
        return self.client.post(
            url,
            {
                "selected_ids": json.dumps(selected_ids),
                "action": action,
            },
        )


class MaterialBulkActionTest(BulkActionTest):
    URL = "/dashboard/materials/action/"

    def test_bulk_delete_removes_selected_materials(self):
        other = Material.objects.create(
            name="Copper Wire",
            category=self.category,
            uom=self.uom,
            company=self.company,
        )
        response = self._post(self.URL, [self.material.pk], "delete")
        self.assertRedirects(response, "/dashboard/materials/")
        self.assertFalse(Material.objects.filter(pk=self.material.pk).exists())
        self.assertTrue(Material.objects.filter(pk=other.pk).exists())

    def test_bulk_activate_and_inactivate_toggle_is_active(self):
        self.material.is_active = False
        self.material.save(update_fields=["is_active"])

        self._post(self.URL, [self.material.pk], "activate")
        self.material.refresh_from_db()
        self.assertTrue(self.material.is_active)

        self._post(self.URL, [self.material.pk], "inactivate")
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_active)

    def test_bulk_delete_keeps_materials_used_by_orders(self):
        order = Order.objects.create(user=self.customer)
        OrderItem.objects.create(
            order=order, material=self.material, quantity=Decimal("1")
        )
        response = self._post(self.URL, [self.material.pk], "delete")
        self.assertRedirects(response, "/dashboard/materials/")
        self.assertTrue(Material.objects.filter(pk=self.material.pk).exists())

    def test_bulk_actions_require_staff(self):
        self.client.logout()
        response = self._post(self.URL, [self.material.pk], "delete")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])
        self.assertTrue(Material.objects.filter(pk=self.material.pk).exists())


class CategoryBulkActionTest(BulkActionTest):
    URL = "/dashboard/categories/action/"

    def test_bulk_delete_removes_non_system_categories(self):
        free = MaterialCategory.objects.create(name="Free Cat")
        response = self._post(self.URL, [free.pk], "delete")
        self.assertRedirects(response, "/dashboard/categories/")
        self.assertFalse(MaterialCategory.objects.filter(pk=free.pk).exists())

    def test_bulk_delete_blocks_system_categories(self):
        MaterialCategory.objects.filter(pk=self.category.pk).update(is_system=True)
        response = self._post(self.URL, [self.category.pk], "delete")
        self.assertRedirects(response, "/dashboard/categories/")
        self.assertTrue(MaterialCategory.objects.filter(pk=self.category.pk).exists())

    def test_bulk_delete_keeps_categories_used_by_materials(self):
        Material.objects.create(
            name="Used",
            category=self.category,
            uom=self.uom,
            company=self.company,
        )
        response = self._post(self.URL, [self.category.pk], "delete")
        self.assertRedirects(response, "/dashboard/categories/")
        self.assertTrue(MaterialCategory.objects.filter(pk=self.category.pk).exists())


class UnitBulkActionTest(BulkActionTest):
    URL = "/dashboard/units/action/"

    def test_bulk_delete_keeps_units_used_by_materials(self):
        response = self._post(self.URL, [self.uom.pk], "delete")
        self.assertRedirects(response, "/dashboard/units/")
        self.assertTrue(UnitOfMeasure.objects.filter(pk=self.uom.pk).exists())


class BannerBulkActionTest(BulkActionTest):
    URL = "/dashboard/banners/action/"

    def test_bulk_activate_and_inactivate_toggle_is_active(self):
        banner = Banner.objects.create(title="Sale", is_active=False)

        self._post(self.URL, [banner.pk], "activate")
        banner.refresh_from_db()
        self.assertTrue(banner.is_active)

        self._post(self.URL, [banner.pk], "inactivate")
        banner.refresh_from_db()
        self.assertFalse(banner.is_active)

    def test_bulk_delete_removes_selected_banners(self):
        banner = Banner.objects.create(title="Doomed")
        response = self._post(self.URL, [banner.pk], "delete")
        self.assertRedirects(response, "/dashboard/banners/")
        self.assertFalse(Banner.objects.filter(pk=banner.pk).exists())


class CustomerBulkActionTest(BulkActionTest):
    URL = "/dashboard/customers/action/"

    def test_bulk_activate_and_inactivate_toggle_is_active(self):
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])

        self._post(self.URL, [self.customer.pk], "activate")
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

        self._post(self.URL, [self.customer.pk], "inactivate")
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_bulk_delete_is_scoped_to_customers(self):
        self._post(self.URL, [self.staff.pk], "delete")
        self.assertTrue(CustomUser.objects.filter(pk=self.staff.pk).exists())

    def test_bulk_delete_keeps_customers_with_orders(self):
        Order.objects.create(user=self.customer)
        response = self._post(self.URL, [self.customer.pk], "delete")
        self.assertRedirects(response, "/dashboard/customers/")
        self.assertTrue(CustomUser.objects.filter(pk=self.customer.pk).exists())

    def test_bulk_delete_removes_unreferenced_customers(self):
        response = self._post(self.URL, [self.customer.pk], "delete")
        self.assertRedirects(response, "/dashboard/customers/")
        self.assertFalse(CustomUser.objects.filter(pk=self.customer.pk).exists())
