from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from tarcom.base.models import (
    CustomUser,
    Material,
    MaterialCategory,
    Order,
    OrderItem,
    UnitOfMeasure,
)
from tarcom.utils.enums import OrderStatus, PaymentMethod, PaymentStatus, UserType

LOCKOUT_MESSAGE = "لقد تم حظر المحاولات"


class DashboardViewTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
        )

    def test_dashboard_redirects_anonymous_user_to_login(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/login/'), response['Location'])

    def test_dashboard_renders_for_staff_user(self):
        # base.html sidebar profile block must not crash on a signed-in staff user
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('hx-get="/dashboard/partial/"', response.content.decode())

    def test_dashboard_partial_returns_stat_cards(self):
        self.client.force_login(self.staff)
        response = self.client.get('/dashboard/partial/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # 8 stat cards, with context variables resolved (no leftover {{ ... }})
        self.assertEqual(body.count('stat-card'), 8)
        self.assertNotIn('_count', body)


class DashboardAuthTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
        )
        self.customer = CustomUser.objects.create_user(
            email='customer@tarcom.com',
            password='CustomerPass123!',
            user_type=UserType.CUSTOMER,
        )
        self.cache_key = 'dashboard_login_attempts_127.0.0.1_staff@tarcom.com'

    def tearDown(self):
        cache.clear()

    def test_dashboard_login_success(self):
        response = self.client.post('/login/', {
            'phonenumber': 'staff@tarcom.com',
            'password': 'StaffPass123!',
        })
        self.assertRedirects(response, '/dashboard/')
        self.assertEqual(self.client.session.get('_auth_user_id'), str(self.staff.pk))
        # a successful login resets the attempt counter
        self.assertIsNone(cache.get(self.cache_key))

    def test_dashboard_login_rate_limiting(self):
        for attempt in (1, 2, 3):
            response = self.client.post('/login/', {
                'phonenumber': 'staff@tarcom.com',
                'password': 'WrongPassword123!',
            })
            self.assertEqual(response.status_code, 200)
            content = response.content.decode()
            if attempt < 3:
                self.assertIn(f'متبقي لديك {3 - attempt} محاولة', content)
            else:
                self.assertIn('تم استنفاد جميع المحاولات', content)

        # 4th attempt is refused even with valid credentials
        response = self.client.post('/login/', {
            'phonenumber': 'staff@tarcom.com',
            'password': 'StaffPass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertIn(LOCKOUT_MESSAGE, response.content.decode())
        # Counter kept with the 15-minute TTL (lockout_duration)
        self.assertEqual(cache.get(self.cache_key), 3)

    def test_non_staff_redirected_from_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get('/dashboard/')
        self.assertRedirects(response, '/login/?next=/dashboard/')

    def test_non_staff_login_rejected(self):
        response = self.client.post('/login/', {
            'phonenumber': 'customer@tarcom.com',
            'password': 'CustomerPass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get('_auth_user_id'))
        self.assertIn('ليس لديه صلاحية الدخول', response.content.decode())


class DashboardMaterialsCrudTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
        )
        self.client.force_login(self.staff)
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.category = MaterialCategory.objects.create(name='Steel')
        self.form_data = {
            'name': 'Steel Rod',
            'category': str(self.category.pk),
            'uom': str(self.uom.pk),
            'supplier_price': '80.00',
            'consumer_price': '100.00',
            'is_active': 'on',
        }

    def test_dashboard_materials_crud(self):
        # Create
        response = self.client.post('/dashboard/materials/create/', self.form_data)
        self.assertRedirects(response, '/dashboard/materials/')
        material = Material.objects.get(name='Steel Rod')
        self.assertEqual(material.category, self.category)
        self.assertEqual(material.uom, self.uom)
        self.assertTrue(material.is_active)

        # List
        response = self.client.get('/dashboard/materials/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Steel Rod')

        # Edit
        edit_data = dict(self.form_data, name='Steel Rod XL', consumer_price='120.00')
        response = self.client.post(f'/dashboard/materials/{material.pk}/edit/', edit_data)
        self.assertRedirects(response, '/dashboard/materials/')
        material.refresh_from_db()
        self.assertEqual(material.name, 'Steel Rod XL')
        self.assertEqual(material.consumer_price, Decimal('120.00'))

        # Delete
        response = self.client.post(f'/dashboard/materials/{material.pk}/delete/')
        self.assertRedirects(response, '/dashboard/materials/')
        self.assertFalse(Material.objects.filter(pk=material.pk).exists())


class DashboardOrdersTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
        )
        self.customer = CustomUser.objects.create_user(
            email='customer@tarcom.com',
            password='CustomerPass123!',
        )
        self.order = Order.objects.create(user=self.customer)
        self.client.force_login(self.staff)

    def test_dashboard_orders_status_update(self):
        # List and detail render for staff
        self.assertEqual(self.client.get('/dashboard/orders/').status_code, 200)
        detail = self.client.get(f'/dashboard/orders/{self.order.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, self.order.order_number)

        response = self.client.post(f'/dashboard/orders/{self.order.pk}/status/', {
            'status': OrderStatus.PENDING,
            'payment_status': PaymentStatus.PAID,
        })
        self.assertRedirects(response, f'/dashboard/orders/{self.order.pk}/')

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_dashboard_orders_list_filters_by_status(self):
        other = Order.objects.create(user=self.customer, status=OrderStatus.SHIPPED)
        response = self.client.get('/dashboard/orders/', {'status': OrderStatus.SHIPPED})
        self.assertEqual(response.status_code, 200)
        orders = list(response.context['orders'])
        self.assertEqual([o.pk for o in orders], [other.pk])


class DashboardUsersCrudTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
        )
        self.client.force_login(self.staff)

    def _payload(self, email, **extra):
        data = {
            'email': email,
            'first_name': 'First',
            'last_name': 'User',
            'phone': '+963912345678',
            # `users-list` is the admins page, so the CRUD flow is exercised with
            # admins to keep the list assertion below meaningful.
            'user_type': UserType.ADMIN,
            'is_active': 'on',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }
        data.update(extra)
        return data

    def test_dashboard_users_crud(self):
        # Two consecutive creates prove the username collision is handled
        response = self.client.post('/dashboard/users/create/', self._payload('first@example.com'))
        self.assertRedirects(response, '/dashboard/users/')
        response = self.client.post('/dashboard/users/create/', self._payload('second@example.com'))
        self.assertRedirects(response, '/dashboard/users/')

        first = CustomUser.objects.get(email='first@example.com')
        self.assertTrue(first.check_password('StrongPass123!'))
        self.assertEqual(first.username, 'first@example.com')

        # List
        response = self.client.get('/dashboard/users/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'first@example.com')

        # Edit (password untouched when left blank)
        edit = self._payload('first@example.com', password='', confirm_password='', first_name='Edited')
        response = self.client.post(f'/dashboard/users/{first.pk}/edit/', edit)
        self.assertRedirects(response, '/dashboard/users/')
        first.refresh_from_db()
        self.assertEqual(first.first_name, 'Edited')
        self.assertTrue(first.check_password('StrongPass123!'))

        # Delete
        response = self.client.post(f'/dashboard/users/{first.pk}/delete/')
        self.assertRedirects(response, '/dashboard/users/')
        self.assertFalse(CustomUser.objects.filter(pk=first.pk).exists())

    def test_dashboard_user_cannot_delete_own_account(self):
        response = self.client.post(f'/dashboard/users/{self.staff.pk}/delete/')
        self.assertRedirects(response, '/dashboard/users/')
        self.assertTrue(CustomUser.objects.filter(pk=self.staff.pk).exists())


class DashboardProtectedDeleteTest(TestCase):
    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
        )
        self.client.force_login(self.staff)
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.category = MaterialCategory.objects.create(name='Steel')
        self.material = Material.objects.create(
            name='Steel Rod',
            category=self.category,
            uom=self.uom,
            consumer_price=Decimal('100.00'),
        )

    def test_protected_records_redirect_with_message_instead_of_500(self):
        # Category and unit are protected by the material that uses them
        for url, pk, model in [
            (f'/dashboard/categories/{self.category.pk}/delete/', self.category.pk, MaterialCategory),
            (f'/dashboard/units/{self.uom.pk}/delete/', self.uom.pk, UnitOfMeasure),
        ]:
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertTrue(model.objects.filter(pk=pk).exists())
            # The flash message rendered on the list page explains why
            followed = self.client.get(response['Location'])
            self.assertEqual(followed.status_code, 200)
            self.assertContains(followed, 'لا يمكن حذف')

    def test_ajax_delete_returns_json_and_deletes(self):
        url = f'/dashboard/materials/{self.material.pk}/delete/'
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['message'], 'تم حذف المادة بنجاح.')
        self.assertFalse(Material.objects.filter(pk=self.material.pk).exists())

    def test_ajax_delete_of_protected_record_returns_error_json(self):
        url = f'/dashboard/categories/{self.category.pk}/delete/'
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertTrue(payload['message'].startswith('لا يمكن حذف'))
        self.assertTrue(MaterialCategory.objects.filter(pk=self.category.pk).exists())

    def test_ajax_delete_of_own_account_returns_error_json(self):
        url = f'/dashboard/users/{self.staff.pk}/delete/'
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertTrue(CustomUser.objects.filter(pk=self.staff.pk).exists())


class DashboardUserPagesTest(TestCase):
    """Admins, customers and suppliers each live on their own page."""

    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
            user_type=UserType.ADMIN,
        )
        self.customer = CustomUser.objects.create_user(
            email='cust@tarcom.com', password='CustPass123!', user_type=UserType.CUSTOMER,
        )
        self.supplier = CustomUser.objects.create_user(
            email='sup@tarcom.com', password='SupPass123!', user_type=UserType.SUPPLIER,
        )
        self.other_admin = CustomUser.objects.create_user(
            email='second-admin@tarcom.com',
            password='AdminPass123!',
            user_type=UserType.ADMIN,
        )
        self.client.force_login(self.staff)

    def test_users_list_shows_only_admins(self):
        response = self.client.get('/dashboard/users/')
        self.assertEqual(response.status_code, 200)
        # Assert on the list, not the rendered HTML: the sidebar prints the
        # signed-in user's email on every page.
        self.assertEqual(
            {u.email for u in response.context['users']},
            {self.staff.email, 'second-admin@tarcom.com'},
        )

    def test_customers_list_shows_only_customers(self):
        response = self.client.get('/dashboard/customers/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({u.email for u in response.context['customers']}, {self.customer.email})
        self.assertNotContains(response, 'sup@tarcom.com')

    def test_suppliers_list_shows_only_suppliers(self):
        response = self.client.get('/dashboard/suppliers/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual({u.email for u in response.context['suppliers']}, {self.supplier.email})
        self.assertNotContains(response, 'cust@tarcom.com')

    def test_lists_are_searchable(self):
        response = self.client.get('/dashboard/customers/', {'q': 'sup@tarcom'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'cust@tarcom.com')

    def test_customer_create_presets_user_type(self):
        payload = {
            'email': 'new-cust@tarcom.com',
            'first_name': 'New',
            'last_name': 'Customer',
            'phone': '+963912345678',
            'user_type': UserType.CUSTOMER,
            'is_active': 'on',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }
        response = self.client.post('/dashboard/customers/create/', payload)
        self.assertRedirects(response, '/dashboard/customers/')
        created = CustomUser.objects.get(email='new-cust@tarcom.com')
        self.assertEqual(created.user_type, UserType.CUSTOMER)
        self.assertTrue(created.check_password('StrongPass123!'))

    def test_supplier_create_presets_user_type(self):
        payload = {
            'email': 'new-sup@tarcom.com',
            'first_name': 'New',
            'last_name': 'Supplier',
            'phone': '+963912345678',
            'user_type': UserType.SUPPLIER,
            'is_active': 'on',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }
        response = self.client.post('/dashboard/suppliers/create/', payload)
        self.assertRedirects(response, '/dashboard/suppliers/')
        created = CustomUser.objects.get(email='new-sup@tarcom.com')
        self.assertEqual(created.user_type, UserType.SUPPLIER)

    def test_customer_form_hides_the_user_type_dropdown(self):
        response = self.client.get('/dashboard/customers/create/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="hidden"')
        self.assertNotContains(response, '<select')

    def test_customer_edit_rejects_a_supplier(self):
        # The update view is scoped to customers, so a supplier is a 404.
        response = self.client.get(f'/dashboard/customers/{self.supplier.pk}/edit/')
        self.assertEqual(response.status_code, 404)

    def test_customer_delete_ajax(self):
        url = f'/dashboard/customers/{self.customer.pk}/delete/'
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['message'], 'تم حذف العميل بنجاح.')
        self.assertFalse(CustomUser.objects.filter(pk=self.customer.pk).exists())

    def test_supplier_delete_ajax(self):
        url = f'/dashboard/suppliers/{self.supplier.pk}/delete/'
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['message'], 'تم حذف المورد بنجاح.')
        self.assertFalse(CustomUser.objects.filter(pk=self.supplier.pk).exists())

    def test_pages_require_staff(self):
        self.client.logout()
        for url in (
            '/dashboard/customers/',
            '/dashboard/suppliers/',
            '/dashboard/users/',
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302, url)
                self.assertIn('/login/', response['Location'])

    def test_customer_delete_url_cannot_delete_a_non_customer(self):
        # DeleteView resolves `model._default_manager.all()` unless the view
        # narrows it, which made every user deletable through the customers URL.
        for victim in (self.staff, self.other_admin, self.supplier):
            with self.subTest(email=victim.email):
                url = f'/dashboard/customers/{victim.pk}/delete/'
                response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
                self.assertEqual(response.status_code, 404, url)
                self.assertTrue(CustomUser.objects.filter(pk=victim.pk).exists())

    def test_supplier_delete_url_cannot_delete_a_non_supplier(self):
        for victim in (self.staff, self.other_admin, self.customer):
            with self.subTest(email=victim.email):
                url = f'/dashboard/suppliers/{victim.pk}/delete/'
                response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
                self.assertEqual(response.status_code, 404, url)
                self.assertTrue(CustomUser.objects.filter(pk=victim.pk).exists())

    def test_customer_create_ignores_a_tampered_user_type(self):
        # The hidden input is client-side editable, so the view must not trust it.
        payload = {
            'email': 'tampered@t.com',
            'first_name': 'T',
            'last_name': 'T',
            'phone': '+963912345678',
            'user_type': UserType.ADMIN,
            'is_active': 'on',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }
        self.client.post('/dashboard/customers/create/', payload)
        self.assertEqual(
            CustomUser.objects.get(email='tampered@t.com').user_type, UserType.CUSTOMER
        )

    def test_supplier_create_ignores_a_tampered_user_type(self):
        payload = {
            'email': 'tampered-sup@t.com',
            'first_name': 'T',
            'last_name': 'T',
            'phone': '+963912345678',
            'user_type': UserType.ADMIN,
            'is_active': 'on',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
        }
        self.client.post('/dashboard/suppliers/create/', payload)
        self.assertEqual(
            CustomUser.objects.get(email='tampered-sup@t.com').user_type, UserType.SUPPLIER
        )

    def test_customer_edit_cannot_grant_staff_or_superuser(self):
        payload = {
            'email': self.customer.email,
            'first_name': 'C',
            'last_name': 'U',
            'phone': '+963912345678',
            'user_type': UserType.ADMIN,
            'is_active': 'on',
            'is_staff': 'on',
            'is_superuser': 'on',
            'password': '',
            'confirm_password': '',
        }
        self.client.post(f'/dashboard/customers/{self.customer.pk}/edit/', payload)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.user_type, UserType.CUSTOMER)
        self.assertFalse(self.customer.is_staff)
        self.assertFalse(self.customer.is_superuser)

    def test_delete_is_refused_for_a_customer_with_orders(self):
        ordered = CustomUser.objects.create_user(
            email='ordered@t.com', password='StrongPass123!', user_type=UserType.CUSTOMER,
        )
        Order.objects.create(user=ordered)
        url = f'/dashboard/customers/{ordered.pk}/delete/'
        response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload['ok'])
        self.assertTrue(payload['message'].startswith('لا يمكن حذف'))
        self.assertTrue(CustomUser.objects.filter(pk=ordered.pk).exists())


class DashboardPageRenderTest(TestCase):
    """Every dashboard route must render (or redirect) without a server error."""

    def setUp(self):
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com',
            password='StaffPass123!',
            is_staff=True,
        )
        self.customer = CustomUser.objects.create_user(
            email='customer@tarcom.com',
            password='CustomerPass123!',
        )
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.category = MaterialCategory.objects.create(name='Steel')
        self.material = Material.objects.create(
            name='Steel Rod',
            category=self.category,
            uom=self.uom,
            consumer_price=Decimal('100.00'),
        )
        self.order = Order.objects.create(user=self.customer)
        self.client.force_login(self.staff)

    def test_dashboard_pages_render(self):
        pages = [
            '/',
            '/dashboard/',
            '/dashboard/users/',
            '/dashboard/users/create/',
            f'/dashboard/users/{self.customer.pk}/edit/',
            '/dashboard/materials/',
            '/dashboard/materials/create/',
            f'/dashboard/materials/{self.material.pk}/edit/',
            '/dashboard/categories/',
            '/dashboard/categories/create/',
            f'/dashboard/categories/{self.category.pk}/edit/',
            '/dashboard/units/',
            '/dashboard/units/create/',
            f'/dashboard/units/{self.uom.pk}/edit/',
            '/dashboard/orders/',
            f'/dashboard/orders/{self.order.pk}/',
            '/change-password/',
        ]
        for url in pages:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

    def test_delete_pages_reject_get(self):
        urls = [
            f'/dashboard/users/{self.customer.pk}/delete/',
            f'/dashboard/materials/{self.material.pk}/delete/',
            f'/dashboard/categories/{self.category.pk}/delete/',
            f'/dashboard/units/{self.uom.pk}/delete/',
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 405, url)

    def test_login_page_renders_for_anonymous_visitor(self):
        self.client.logout()
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'login-form')

    def test_logout_ends_the_session(self):
        response = self.client.post('/logout/')
        self.assertRedirects(response, '/login/')
        self.assertIsNone(self.client.session.get('_auth_user_id'))


class OrderModelTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='customer@example.com',
            password='TestPassword123!',
        )
        self.uom = UnitOfMeasure.objects.create(name='Piece', code='PCS')
        self.category = MaterialCategory.objects.create(name='Steel')
        self.material1 = Material.objects.create(
            name='Steel Rod',
            category=self.category,
            uom=self.uom,
            consumer_price=Decimal('100.00'),
            supplier_price=Decimal('80.00'),
        )
        self.material2 = Material.objects.create(
            name='Steel Sheet',
            category=self.category,
            uom=self.uom,
            consumer_price=Decimal('50.00'),
            supplier_price=Decimal('40.00'),
        )

    def test_order_creation_auto_generates_order_number(self):
        order = Order.objects.create(user=self.user)
        self.assertIsNotNone(order.order_number)
        self.assertTrue(order.order_number.startswith('ORD-'))
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.payment_status, PaymentStatus.UNPAID)
        self.assertEqual(order.payment_method, PaymentMethod.CASH)

    def test_order_item_line_total_and_order_total_calculation(self):
        order = Order.objects.create(user=self.user, discount_amount=Decimal('10.00'))
        item1 = OrderItem.objects.create(
            order=order,
            material=self.material1,
            quantity=Decimal('2.000'),
            unit_price=Decimal('100.00'),
            discount_amount=Decimal('5.00'),
        )
        # Line total = (2 * 100) - 5 = 195.00
        self.assertEqual(item1.line_total, Decimal('195.00'))

        item2 = OrderItem.objects.create(
            order=order,
            material=self.material2,
            quantity=Decimal('3.000'),
            # Auto defaults to consumer_price (50.00)
        )
        # Line total = 3 * 50 = 150.00
        self.assertEqual(item2.line_total, Decimal('150.00'))

        order.refresh_from_db()
        # Subtotal = 195 + 150 = 345.00, Total = 345 - 10 = 335.00
        self.assertEqual(order.subtotal, Decimal('345.00'))
        self.assertEqual(order.total_amount, Decimal('335.00'))

    def test_deleting_order_item_recalculates_order_totals(self):
        order = Order.objects.create(user=self.user)
        item1 = OrderItem.objects.create(
            order=order,
            material=self.material1,
            quantity=Decimal('1.000'),
            unit_price=Decimal('100.00'),
        )
        item2 = OrderItem.objects.create(
            order=order,
            material=self.material2,
            quantity=Decimal('1.000'),
            unit_price=Decimal('50.00'),
        )
        order.refresh_from_db()
        self.assertEqual(order.subtotal, Decimal('150.00'))

        item2.delete()
        order.refresh_from_db()
        self.assertEqual(order.subtotal, Decimal('100.00'))
        self.assertEqual(order.total_amount, Decimal('100.00'))

    def test_duplicate_material_in_same_order_raises_integrity_error(self):
        order = Order.objects.create(user=self.user)
        OrderItem.objects.create(order=order, material=self.material1, quantity=Decimal('1.000'))
        with self.assertRaises(IntegrityError):
            OrderItem.objects.create(order=order, material=self.material1, quantity=Decimal('2.000'))

    def test_negative_values_raise_validation_error(self):
        order = Order.objects.create(user=self.user)
        invalid_item = OrderItem(
            order=order,
            material=self.material1,
            quantity=Decimal('-1.000'),
        )
        with self.assertRaises(ValidationError):
            invalid_item.clean()
