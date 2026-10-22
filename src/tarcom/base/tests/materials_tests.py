import json
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from tarcom.base.models import (
    Company,
    CustomUser,
    Material,
    MaterialCategory,
    Setting,
    UnitOfMeasure,
)
from tarcom.utils.enums import FeatureReason


class DashboardMaterialsCrudTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.client.force_login(self.staff)
        self.uom = UnitOfMeasure.objects.create(name="Piece", code="PCS")
        self.category = MaterialCategory.objects.create(name="Steel")
        self.company = Company.objects.create(name="Steel Co")
        self.form_data = {
            "name_en": "Steel Rod",
            "name_ar": "قضيب فولاذي",
            "category": str(self.category.pk),
            "uom": str(self.uom.pk),
            "company": str(self.company.pk),
            "supplier_price": "80.00",
            "consumer_price": "100.00",
            "is_active": "on",
        }

    def test_dashboard_materials_crud(self):
        # Create
        response = self.client.post(
            "/dashboard/materials/create/",
            dict(
                self.form_data,
                info_file=SimpleUploadedFile(
                    "datasheet.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
                ),
            ),
        )
        self.assertRedirects(response, "/dashboard/materials/")
        material = Material.objects.get(name="Steel Rod")
        self.assertEqual(material.category, self.category)
        self.assertEqual(material.uom, self.uom)
        self.assertEqual(material.company, self.company)
        self.assertTrue(material.is_active)
        self.assertTrue(
            str(material.info_file.name).startswith("files/materials/")
        )

        # List
        response = self.client.get("/dashboard/materials/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "قضيب فولاذي")

        # Edit form exposes the info_file field
        response = self.client.get(f"/dashboard/materials/{material.pk}/edit/")
        self.assertContains(response, 'name="info_file"')

        # Edit
        edit_data = dict(
            self.form_data, name_en="Steel Rod XL", consumer_price="120.00"
        )
        response = self.client.post(
            f"/dashboard/materials/{material.pk}/edit/", edit_data
        )
        self.assertRedirects(response, "/dashboard/materials/")
        material.refresh_from_db()
        self.assertEqual(material.name, "Steel Rod XL")
        self.assertEqual(material.consumer_price, Decimal("120.00"))

        # Delete
        response = self.client.post(f"/dashboard/materials/{material.pk}/delete/")
        self.assertRedirects(response, "/dashboard/materials/")
        self.assertFalse(Material.objects.filter(pk=material.pk).exists())

    def test_material_form_exposes_read_only_sp_fields(self):
        response = self.client.get("/dashboard/materials/create/")
        self.assertContains(response, 'name="supplier_price_in_sp"')
        self.assertContains(response, 'name="consumer_price_in_sp"')
        self.assertContains(response, "readonly")

    def test_material_edit_form_shows_converted_sp_values(self):
        Setting.objects.create(key="conversion_price", value="140")
        material = Material.objects.create(
            name="Rod",
            category=self.category,
            uom=self.uom,
            company=self.company,
            supplier_price=Decimal("80.00"),
            consumer_price=Decimal("100.00"),
        )
        response = self.client.get(f"/dashboard/materials/{material.pk}/edit/")
        self.assertContains(response, 'value="11200.00"')
        self.assertContains(response, 'value="14000.00"')

    def test_material_list_shows_sp_prices_next_to_usd_prices(self):
        Setting.objects.create(key="conversion_price", value="140")
        Material.objects.create(
            name="Rod",
            category=self.category,
            uom=self.uom,
            company=self.company,
            supplier_price=Decimal("80.00"),
            consumer_price=Decimal("100.00"),
        )
        response = self.client.get("/dashboard/materials/")
        self.assertContains(response, "80.00")
        self.assertContains(response, "11200.00")
        self.assertContains(response, "100.00")
        self.assertContains(response, "14000.00")


class DashboardMaterialFeaturesTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.client.force_login(self.staff)
        self.uom = UnitOfMeasure.objects.create(name="Piece", code="PCS")
        self.category = MaterialCategory.objects.create(
            name="Steel", name_en="Steel", name_ar="حديد"
        )
        self.company = Company.objects.create(name="Steel Co")
        self.materials = [
            Material.objects.create(
                name=f"Material {index}",
                name_en=f"Material {index}",
                name_ar=f"مادة {index}",
                category=self.category,
                uom=self.uom,
                company=self.company,
                consumer_price=Decimal("10.00"),
            )
            for index in range(12)
        ]

    def test_page_renders_for_staff_and_redirects_anonymous(self):
        response = self.client.get("/dashboard/materials/features/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مادة 0")
        self.client.logout()
        response = self.client.get("/dashboard/materials/features/")
        self.assertEqual(response.status_code, 302)

    def test_bulk_marks_features_and_unchecking_clears_reason(self):
        first, second = self.materials[0], self.materials[1]
        response = self.client.post(
            "/dashboard/materials/features/",
            {
                f"feature_{first.pk}": "1",
                f"reason_{first.pk}": FeatureReason.OFFER,
                f"feature_{second.pk}": "1",
                f"reason_{second.pk}": FeatureReason.LIMITED_TIME,
            },
        )
        self.assertRedirects(response, "/dashboard/materials/features/")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(first.is_feature)
        self.assertEqual(first.feature_reason, FeatureReason.OFFER)
        self.assertTrue(second.is_feature)
        self.assertEqual(second.feature_reason, FeatureReason.LIMITED_TIME)

        response = self.client.post(
            "/dashboard/materials/features/",
            {f"feature_{second.pk}": "1", f"reason_{second.pk}": FeatureReason.SPECIAL},
        )
        self.assertRedirects(response, "/dashboard/materials/features/")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_feature)
        self.assertEqual(first.feature_reason, "")
        self.assertEqual(second.feature_reason, FeatureReason.SPECIAL)

    def test_checked_without_reason_is_rejected(self):
        material = self.materials[0]
        response = self.client.post(
            "/dashboard/materials/features/",
            {f"feature_{material.pk}": "1", f"reason_{material.pk}": ""},
        )
        self.assertEqual(response.status_code, 200)
        material.refresh_from_db()
        self.assertFalse(material.is_feature)
        self.assertEqual(material.feature_reason, "")

    def test_ten_features_are_allowed(self):
        payload = {}
        for material in self.materials[:10]:
            payload[f"feature_{material.pk}"] = "1"
            payload[f"reason_{material.pk}"] = FeatureReason.OFFER
        response = self.client.post("/dashboard/materials/features/", payload)
        self.assertRedirects(response, "/dashboard/materials/features/")
        self.assertEqual(Material.objects.filter(is_feature=True).count(), 10)

    def test_cannot_feature_more_than_ten_materials(self):
        payload = {}
        for material in self.materials[:11]:
            payload[f"feature_{material.pk}"] = "1"
            payload[f"reason_{material.pk}"] = FeatureReason.OFFER
        response = self.client.post("/dashboard/materials/features/", payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Material.objects.filter(is_feature=True).exists())

    def test_cap_counts_featured_materials_hidden_by_filter(self):
        for material in self.materials[:10]:
            material.is_feature = True
            material.feature_reason = FeatureReason.OFFER
            material.save()
        visible = self.materials[10]
        # The search filter hides the 10 already-featured materials, but the
        # server-side cap must still count them.
        response = self.client.post(
            "/dashboard/materials/features/",
            {f"feature_{visible.pk}": "1", f"reason_{visible.pk}": FeatureReason.SPECIAL},
            QUERY_STRING=f"q={visible.name}",
        )
        self.assertEqual(response.status_code, 200)
        visible.refresh_from_db()
        self.assertFalse(visible.is_feature)

    def test_htmx_post_error_returns_rows_and_alert_trigger(self):
        material = self.materials[0]
        response = self.client.post(
            "/dashboard/materials/features/",
            {f"feature_{material.pk}": "1", f"reason_{material.pk}": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<html", response.content)
        self.assertContains(response, "feature-checkbox")
        trigger = json.loads(response["HX-Trigger"])
        self.assertIn("يرجى تحديد سبب التمييز", trigger["featuresMessage"][0])
        # Htmx errors must not leak into the session messages: a later full
        # page load should have nothing to alert.
        page = self.client.get("/dashboard/materials/features/")
        self.assertEqual(list(page.context["messages"]), [])

    def test_htmx_post_success_swaps_rows_without_redirect(self):
        first = self.materials[0]
        response = self.client.post(
            "/dashboard/materials/features/",
            {f"feature_{first.pk}": "1", f"reason_{first.pk}": FeatureReason.OFFER},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<html", response.content)
        first.refresh_from_db()
        self.assertTrue(first.is_feature)
        self.assertEqual(first.feature_reason, FeatureReason.OFFER)
        trigger = json.loads(response["HX-Trigger"])
        self.assertEqual(trigger["featuresMessage"], ["تم تحديث المواد المميزة بنجاح."])
        page = self.client.get("/dashboard/materials/features/")
        self.assertEqual(list(page.context["messages"]), [])
