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

    def test_category_form_exposes_internal_name(self):
        self.assertIn("internal_name", CategoryForm().fields)

    def test_create_category_via_dashboard(self):
        response = self.client.post(
            "/dashboard/categories/create/",
            {"name_en": "Accessories", "name_ar": "إكسسوارات"},
        )
        self.assertRedirects(response, "/dashboard/categories/")
        category = MaterialCategory.objects.get(name_en="Accessories")
        self.assertFalse(category.image)

    def test_create_category_with_internal_name(self):
        response = self.client.post(
            "/dashboard/categories/create/",
            {
                "name_en": "Accessories",
                "name_ar": "إكسسوارات",
                "internal_name": "accessories",
            },
        )
        self.assertRedirects(response, "/dashboard/categories/")
        category = MaterialCategory.objects.get(name_en="Accessories")
        self.assertEqual(category.internal_name, "accessories")
        self.assertFalse(category.is_system)

    def test_blank_internal_name_saves_as_null_for_every_category(self):
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
            MaterialCategory.objects.filter(internal_name__isnull=True).count(), 2
        )

    def test_duplicate_internal_name_is_rejected(self):
        MaterialCategory.objects.create(
            name="Accessories", name_en="Accessories", internal_name="accessories"
        )
        response = self.client.post(
            "/dashboard/categories/create/",
            {
                "name_en": "Wearables",
                "name_ar": "قابلة للارتداء",
                "internal_name": "accessories",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("internal_name", response.context["form"].errors)
        self.assertFalse(MaterialCategory.objects.filter(name_en="Wearables").exists())
