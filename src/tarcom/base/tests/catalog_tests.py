from django.test import TestCase

from tarcom.base.forms import CategoryForm
from tarcom.base.models import CustomUser, MaterialCategory


class DashboardCategoryTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_category_form_exposes_image(self):
        form = CategoryForm()
        self.assertIn("image", form.fields)

    def test_category_form_does_not_expose_internal_name(self):
        self.assertNotIn("internal_name", CategoryForm().fields)

    def test_create_category_via_dashboard(self):
        response = self.client.post(
            "/dashboard/categories/create/",
            {"name_en": "Accessories", "name_ar": "إكسسوارات"},
        )
        self.assertRedirects(response, "/dashboard/categories/")
        category = MaterialCategory.objects.get(name_en="Accessories")
        self.assertFalse(category.image)

    def test_create_category_auto_generates_internal_name(self):
        response = self.client.post(
            "/dashboard/categories/create/",
            {"name_en": "Solar Boards", "name_ar": "ألواح"},
        )
        self.assertRedirects(response, "/dashboard/categories/")
        category = MaterialCategory.objects.get(name_en="Solar Boards")
        self.assertEqual(category.internal_name, "solar_boards")
        self.assertFalse(category.is_system)

    def test_every_created_category_gets_an_internal_name(self):
        for name_en, name_ar in (
            ("Accessories", "إكسسوارات"),
            ("Wearables", "أجهزة قابلة للارتداء"),
        ):
            response = self.client.post(
                "/dashboard/categories/create/",
                {"name_en": name_en, "name_ar": name_ar},
            )
            self.assertRedirects(response, "/dashboard/categories/")
        self.assertEqual(
            set(
                MaterialCategory.objects.values_list("internal_name", flat=True)
            ),
            {"accessories", "wearables"},
        )

    def test_renaming_a_category_keeps_its_internal_name(self):
        response = self.client.post(
            "/dashboard/categories/create/",
            {"name_en": "Accessories", "name_ar": "إكسسوارات"},
        )
        self.assertRedirects(response, "/dashboard/categories/")
        category = MaterialCategory.objects.get(internal_name="accessories")

        self.client.post(
            f"/dashboard/categories/{category.pk}/edit/",
            {"name_en": "Gadgets", "name_ar": "أدوات"},
        )
        category.refresh_from_db()
        self.assertEqual(category.name_en, "Gadgets")
        self.assertEqual(category.internal_name, "accessories")
