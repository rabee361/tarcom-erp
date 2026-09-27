from django.test import TestCase


class DashboardViewTest(TestCase):
    def test_dashboard_renders_for_anonymous_user(self):
        # base.html sidebar profile block must not crash on AnonymousUser
        # (request.user.email / user_type do not exist for anonymous).
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('hx-get="/dashboard/partial/"', response.content.decode())

    def test_dashboard_partial_returns_stat_cards(self):
        response = self.client.get('/dashboard/partial/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # 8 stat cards, with context variables resolved (no leftover {{ ... }})
        self.assertEqual(body.count('stat-card'), 8)
        self.assertNotIn('_count', body)
