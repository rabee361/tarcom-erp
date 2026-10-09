from django.core.cache import cache
from django.test import TestCase

from tarcom.base.models import CustomUser
from tarcom.utils.enums import UserType

LOCKOUT_MESSAGE = "لقد تم حظر المحاولات"


class DashboardAuthTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = CustomUser.objects.create_user(
            email="staff@tarcom.com",
            password="StaffPass123!",
            is_staff=True,
        )
        self.customer = CustomUser.objects.create_user(
            email="customer@tarcom.com",
            password="CustomerPass123!",
            user_type=UserType.CUSTOMER,
        )
        self.cache_key = "dashboard_login_attempts_127.0.0.1_staff@tarcom.com"

    def tearDown(self):
        cache.clear()

    def test_dashboard_login_success(self):
        response = self.client.post(
            "/login/",
            {
                "phonenumber": "staff@tarcom.com",
                "password": "StaffPass123!",
            },
        )
        self.assertRedirects(response, "/dashboard/")
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.staff.pk))
        # a successful login resets the attempt counter
        self.assertIsNone(cache.get(self.cache_key))

    def test_dashboard_login_rate_limiting(self):
        for attempt in (1, 2, 3):
            response = self.client.post(
                "/login/",
                {
                    "phonenumber": "staff@tarcom.com",
                    "password": "WrongPassword123!",
                },
            )
            self.assertEqual(response.status_code, 200)
            content = response.content.decode()
            if attempt < 3:
                self.assertIn(f"متبقي لديك {3 - attempt} محاولة", content)
            else:
                self.assertIn("تم استنفاد جميع المحاولات", content)

        # 4th attempt is refused even with valid credentials
        response = self.client.post(
            "/login/",
            {
                "phonenumber": "staff@tarcom.com",
                "password": "StaffPass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn(LOCKOUT_MESSAGE, response.content.decode())
        # Counter kept with the 15-minute TTL (lockout_duration)
        self.assertEqual(cache.get(self.cache_key), 3)

    def test_non_staff_redirected_from_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get("/dashboard/")
        self.assertRedirects(response, "/login/?next=/dashboard/")

    def test_non_staff_login_rejected(self):
        response = self.client.post(
            "/login/",
            {
                "phonenumber": "customer@tarcom.com",
                "password": "CustomerPass123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))
        self.assertIn("ليس لديه صلاحية الدخول", response.content.decode())
