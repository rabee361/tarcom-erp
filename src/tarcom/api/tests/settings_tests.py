from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from tarcom.base.models import Banner, Contact, CustomUser, Setting


class SettingsAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = CustomUser.objects.create_superuser(
            email="admin@tarcom.com", password="AdminPass123!"
        )
        self.customer = CustomUser.objects.create_user(
            email="customer@example.com", password="StrongPass123!", is_verified=True
        )
        self.setting = Setting.objects.create(key="SITE_NAME", value="Tarcom")

    def test_create_setting_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/api/settings/",
            {"key": "SUPPORT_PHONE", "value": "069000"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["key"], "SUPPORT_PHONE")
        self.assertTrue(Setting.objects.filter(key="SUPPORT_PHONE").exists())

    def test_create_duplicate_key_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/api/settings/",
            {"key": "SITE_NAME", "value": "Other"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_setting_requires_admin(self):
        anon = self.client.post(
            "/api/settings/", {"key": "K", "value": "V"}, format="json"
        )
        self.assertEqual(anon.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.customer)
        forbidden = self.client.post(
            "/api/settings/", {"key": "K", "value": "V"}, format="json"
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_setting_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            f"/api/settings/{self.setting.pk}/", {"value": "Tarcom Store"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "Tarcom Store")

    def test_non_admin_cannot_update_setting(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.patch(
            f"/api/settings/{self.setting.pk}/", {"value": "Hijacked"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.setting.refresh_from_db()
        self.assertEqual(self.setting.value, "Tarcom")

    def test_delete_setting_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f"/api/settings/{self.setting.pk}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Setting.objects.filter(pk=self.setting.pk).exists())


class ContactAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = CustomUser.objects.create_superuser(
            email="admin@tarcom.com", password="AdminPass123!"
        )

    def test_info_returns_singleton_contact(self):
        contact = Contact.get_solo()
        contact.phone1 = "0111111111"
        contact.phone2 = "0222222222"
        contact.email = "info@tarcom.com"
        contact.address = "Damascus, Syria"
        contact.save()

        response = self.client.get("/api/contact/info/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone1"], "0111111111")
        self.assertEqual(response.data["phone2"], "0222222222")
        self.assertEqual(response.data["email"], "info@tarcom.com")
        self.assertEqual(response.data["address"], "Damascus, Syria")

    def test_info_is_public(self):
        response = self.client.get("/api/contact/info/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_info_creates_contact_when_missing(self):
        self.assertEqual(Contact.objects.count(), 0)
        response = self.client.get("/api/contact/info/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Contact.objects.count(), 1)

    def test_only_info_route_is_exposed(self):
        response = self.client.get("/api/contact/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Non-safe methods hit the permission check first, so authenticate
        # an admin to prove POST is not routed even when permitted.
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/contact/info/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_contact_is_a_singleton(self):
        first = Contact.get_solo()
        first.phone1 = "0111111111"
        first.save()

        # A second instance overwrites the same row instead of adding a new one.
        Contact(
            phone1="0999999999",
            phone2="0888888888",
            email="second@tarcom.com",
            address="Address two",
        ).save()

        self.assertEqual(Contact.objects.count(), 1)
        only = Contact.get_solo()
        self.assertEqual(only.phone1, "0999999999")
        self.assertEqual(only.email, "second@tarcom.com")


class BannerAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_list_banners_is_public(self):
        response = self.client.get("/api/banners/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_returns_only_active_banners(self):
        Banner.objects.create(title="Active", is_active=True)
        Banner.objects.create(title="Hidden", is_active=False)

        response = self.client.get("/api/banners/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Active")

    def test_banner_without_image_returns_null(self):
        Banner.objects.create(title="No image")
        response = self.client.get("/api/banners/")
        self.assertIsNone(response.data[0]["image"])
