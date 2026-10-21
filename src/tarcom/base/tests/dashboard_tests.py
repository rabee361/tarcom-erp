import io
import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from tarcom.base.models import (
    Banner,
    Company,
    Contact,
    CustomUser,
    Material,
    MaterialCategory,
    # Order,
    UnitOfMeasure,
)
from tarcom.utils.enums import UserType

TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="tarcom_test_media_")


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


def jpeg_bytes(size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(30, 60, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


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
        self.company = Company.objects.create(name="Steel Co")
        self.material = Material.objects.create(
            name="Steel Rod",
            category=self.category,
            uom=self.uom,
            company=self.company,
            consumer_price=Decimal("100.00"),
        )
        # self.order = Order.objects.create(user=self.customer)
        self.banner = Banner.objects.create(title="Welcome")
        self.client.force_login(self.staff)

    def test_dashboard_pages_render(self):
        pages = [
            "/",
            "/dashboard/",
            "/dashboard/admins/",
            "/dashboard/admins/create/",
            f"/dashboard/admins/{self.customer.pk}/edit/",
            "/dashboard/customers/",
            "/dashboard/customers/create/",
            "/dashboard/suppliers/",
            "/dashboard/suppliers/create/",
            "/dashboard/materials/",
            "/dashboard/materials/create/",
            f"/dashboard/materials/{self.material.pk}/edit/",
            "/dashboard/categories/",
            "/dashboard/categories/create/",
            f"/dashboard/categories/{self.category.pk}/edit/",
            "/dashboard/units/",
            "/dashboard/units/create/",
            f"/dashboard/units/{self.uom.pk}/edit/",
            "/dashboard/companies/",
            "/dashboard/companies/create/",
            f"/dashboard/companies/{self.company.pk}/edit/",
            "/dashboard/contact/",
            "/dashboard/banners/",
            "/dashboard/banners/create/",
            # f"/dashboard/banners/{self.banner.pk}/edit/",
            # "/dashboard/orders/",
            # f"/dashboard/orders/{self.order.pk}/",
            # "/change-password/",
        ]
        for url in pages:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_delete_pages_reject_get(self):
        urls = [
            f"/dashboard/admins/{self.customer.pk}/delete/",
            f"/dashboard/materials/{self.material.pk}/delete/",
            f"/dashboard/categories/{self.category.pk}/delete/",
            f"/dashboard/units/{self.uom.pk}/delete/",
            f"/dashboard/companies/{self.company.pk}/delete/",
            f"/dashboard/banners/{self.banner.pk}/delete/",
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


class ContactDashboardTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_contact_form_renders(self):
        response = self.client.get("/dashboard/contact/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="phone1"')
        self.assertContains(response, 'name="address"')

    def test_update_contact_persists_singleton(self):
        response = self.client.post(
            "/dashboard/contact/",
            {
                "phone1": "123456789",
                "phone2": "987654321",
                "email": "info@tarcom.com",
                "address": "Main Street",
                "facebook": "https://facebook.com/tarcom",
            },
        )
        self.assertRedirects(response, "/dashboard/contact/")
        self.assertEqual(Contact.objects.count(), 1)
        contact = Contact.get_solo()
        self.assertEqual(contact.phone1, "123456789")
        self.assertEqual(contact.phone2, "987654321")
        self.assertEqual(contact.email, "info@tarcom.com")
        self.assertEqual(contact.address, "Main Street")
        self.assertEqual(contact.facebook, "https://facebook.com/tarcom")

    def test_update_contact_updates_existing_row(self):
        Contact.objects.create(phone1="111", phone2="222", address="Old address")
        self.client.post(
            "/dashboard/contact/",
            {"phone1": "333", "phone2": "444", "email": "", "address": "New address", "facebook": "https://facebook.com/tarcom"},
        )
        self.assertEqual(Contact.objects.count(), 1)
        contact = Contact.get_solo()
        self.assertEqual(contact.phone1, "333")
        self.assertEqual(contact.address, "New address")
        self.assertEqual(contact.facebook, "https://facebook.com/tarcom")
        self.assertIsNone(contact.email)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class BannerDashboardTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def test_create_banner_via_dashboard(self):
        response = self.client.post(
            "/dashboard/banners/create/",
            {"title": "تخفيضات الشتاء", "is_active": "on"},
        )
        self.assertRedirects(response, "/dashboard/banners/")
        banner = Banner.objects.get(title="تخفيضات الشتاء")
        self.assertEqual(banner.title, "تخفيضات الشتاء")
        self.assertTrue(banner.is_active)

    def test_create_banner_persists_uploaded_image(self):
        # Regression: banner_form.html was missing enctype="multipart/form-data",
        # so the file never reached request.FILES and image saved as null.
        response = self.client.post(
            "/dashboard/banners/create/",
            {
                "title": "Winter Sale",
                "is_active": "on",
                "image": SimpleUploadedFile(
                    "banner.jpg", jpeg_bytes(), content_type="image/jpeg"
                ),
            },
        )
        self.assertRedirects(response, "/dashboard/banners/")
        banner = Banner.objects.get(title="Winter Sale")
        self.assertTrue(banner.image)
        self.assertTrue(str(banner.image.name).startswith("images/banners/"))

    def test_update_banner_via_dashboard(self):
        banner = Banner.objects.create(title="Old")
        response = self.client.post(
            f"/dashboard/banners/{banner.pk}/edit/",
            {"title": "جديد", "is_active": "on"},
        )
        self.assertRedirects(response, "/dashboard/banners/")
        banner.refresh_from_db()
        self.assertEqual(banner.title, "جديد")

    def test_delete_banner_via_dashboard(self):
        banner = Banner.objects.create(title="Doomed")
        response = self.client.post(f"/dashboard/banners/{banner.pk}/delete/")
        self.assertRedirects(response, "/dashboard/banners/")
        self.assertFalse(Banner.objects.filter(pk=banner.pk).exists())

    def test_banner_search_matches_title(self):
        Banner.objects.create(title="Summer Sale")
        Banner.objects.create(title="عرض خاص")
        response = self.client.get("/dashboard/banners/", {"q": "summ"})
        self.assertContains(response, "Summer Sale")
        response = self.client.get("/dashboard/banners/", {"q": "عرض"})
        self.assertContains(response, "عرض خاص")
