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

    def test_create_category_via_dashboard(self):
        response = self.client.post(
            "/dashboard/categories/create/",
            {"name_en": "Accessories", "name_ar": "إكسسوارات"},
        )
        self.assertRedirects(response, "/dashboard/categories/")
        category = MaterialCategory.objects.get(name_en="Accessories")
        self.assertFalse(category.image)
