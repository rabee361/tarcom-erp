from django.test import TestCase
from django.utils import translation

from tarcom.base.models import CustomUser, Setting


class DashboardSettingsTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.setting = Setting.objects.create(
            key_en="conversion_price", key_ar="سعر الصرف", value="140"
        )

    def test_settings_page_renders_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get("/dashboard/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "conversion_price")
        self.assertContains(response, "سعر الصرف")
        self.assertContains(response, 'value="140"')

    def test_settings_page_requires_login(self):
        response = self.client.get("/dashboard/settings/")
        self.assertEqual(response.status_code, 302)

    def test_post_updates_setting_value(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            "/dashboard/settings/", {"conversion_price": "150"}
        )
        self.assertRedirects(response, "/dashboard/settings/")
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "150")

    def test_post_rejects_non_numeric_conversion_price(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            "/dashboard/settings/", {"conversion_price": "abc"}
        )
        self.assertEqual(response.status_code, 200)
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "140")

    def test_form_lists_all_settings_and_updates_text_values(self):
        Setting.objects.create(
            key_en="SUPPORT_PHONE", key_ar="رقم الدعم", value="069000"
        )
        self.client.force_login(self.staff)

        response = self.client.get("/dashboard/settings/")
        self.assertContains(response, "SUPPORT_PHONE")
        self.assertContains(response, "رقم الدعم")

        response = self.client.post(
            "/dashboard/settings/",
            {"conversion_price": "150", "SUPPORT_PHONE": "099111"},
        )
        self.assertRedirects(response, "/dashboard/settings/")
        self.assertEqual(Setting.objects.get(key_en="SUPPORT_PHONE").value, "099111")

    def test_form_field_names_and_labels_work_under_arabic_language(self):
        self.client.force_login(self.staff)
        with translation.override("ar"):
            response = self.client.get("/dashboard/settings/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "سعر الصرف")
            self.assertContains(response, 'name="conversion_price"')

            response = self.client.post(
                "/dashboard/settings/", {"conversion_price": "160"}
            )
            self.assertRedirects(response, "/dashboard/settings/")
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "160")
