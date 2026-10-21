# from decimal import Decimal

# from django.core.exceptions import ValidationError
# from django.db import IntegrityError
# from django.test import TestCase

# from tarcom.base.models import (
#     Company,
#     CustomUser,
#     Material,
#     MaterialCategory,
#     Order,
#     OrderItem,
#     UnitOfMeasure,
# )
# from tarcom.utils.enums import OrderStatus, PaymentMethod, PaymentStatus


# class DashboardOrdersTest(TestCase):
#     def setUp(self):
#         self.staff = CustomUser.objects.create_user(
#             email="staff@tarcom.com",
#             password="StaffPass123!",
#             is_staff=True,
#         )
#         self.customer = CustomUser.objects.create_user(
#             email="customer@tarcom.com",
#             password="CustomerPass123!",
#         )
#         self.order = Order.objects.create(user=self.customer)
#         self.client.force_login(self.staff)

#     def test_dashboard_orders_status_update(self):
#         # List and detail render for staff
#         self.assertEqual(self.client.get("/dashboard/orders/").status_code, 200)
#         detail = self.client.get(f"/dashboard/orders/{self.order.pk}/")
#         self.assertEqual(detail.status_code, 200)
#         self.assertContains(detail, self.order.order_number)

#         response = self.client.post(
#             f"/dashboard/orders/{self.order.pk}/status/",
#             {
#                 "status": OrderStatus.PENDING,
#                 "payment_status": PaymentStatus.PAID,
#             },
#         )
#         self.assertRedirects(response, f"/dashboard/orders/{self.order.pk}/")

#         self.order.refresh_from_db()
#         self.assertEqual(self.order.status, OrderStatus.PENDING)
#         self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

#     def test_dashboard_orders_list_filters_by_status(self):
#         other = Order.objects.create(user=self.customer, status=OrderStatus.SHIPPED)
#         response = self.client.get(
#             "/dashboard/orders/", {"status": OrderStatus.SHIPPED}
#         )
#         self.assertEqual(response.status_code, 200)
#         orders = list(response.context["orders"])
#         self.assertEqual([o.pk for o in orders], [other.pk])


# class OrderModelTest(TestCase):
#     def setUp(self):
#         self.user = CustomUser.objects.create_user(
#             email="customer@example.com",
#             password="TestPassword123!",
#         )
#         self.uom = UnitOfMeasure.objects.create(name="Piece", code="PCS")
#         self.category = MaterialCategory.objects.create(name="Steel")
#         self.company = Company.objects.create(name="Steel Co")
#         self.material1 = Material.objects.create(
#             name="Steel Rod",
#             category=self.category,
#             uom=self.uom,
#             company=self.company,
#             consumer_price=Decimal("100.00"),
#             supplier_price=Decimal("80.00"),
#         )
#         self.material2 = Material.objects.create(
#             name="Steel Sheet",
#             category=self.category,
#             uom=self.uom,
#             company=self.company,
#             consumer_price=Decimal("50.00"),
#             supplier_price=Decimal("40.00"),
#         )

#     def test_order_creation_auto_generates_order_number(self):
#         order = Order.objects.create(user=self.user)
#         self.assertIsNotNone(order.order_number)
#         self.assertTrue(order.order_number.startswith("ORD-"))
#         self.assertEqual(order.status, OrderStatus.PENDING)
#         self.assertEqual(order.payment_status, PaymentStatus.UNPAID)
#         self.assertEqual(order.payment_method, PaymentMethod.CASH)

#     def test_order_item_line_total_and_order_total_calculation(self):
#         order = Order.objects.create(user=self.user, discount_amount=Decimal("10.00"))
#         item1 = OrderItem.objects.create(
#             order=order,
#             material=self.material1,
#             quantity=Decimal("2.000"),
#             unit_price=Decimal("100.00"),
#             discount_amount=Decimal("5.00"),
#         )
#         # Line total = (2 * 100) - 5 = 195.00
#         self.assertEqual(item1.line_total, Decimal("195.00"))

#         item2 = OrderItem.objects.create(
#             order=order,
#             material=self.material2,
#             quantity=Decimal("3.000"),
#             # Auto defaults to consumer_price (50.00)
#         )
#         # Line total = 3 * 50 = 150.00
#         self.assertEqual(item2.line_total, Decimal("150.00"))

#         order.refresh_from_db()
#         # Subtotal = 195 + 150 = 345.00, Total = 345 - 10 = 335.00
#         self.assertEqual(order.subtotal, Decimal("345.00"))
#         self.assertEqual(order.total_amount, Decimal("335.00"))

#     def test_deleting_order_item_recalculates_order_totals(self):
#         order = Order.objects.create(user=self.user)
#         item1 = OrderItem.objects.create(
#             order=order,
#             material=self.material1,
#             quantity=Decimal("1.000"),
#             unit_price=Decimal("100.00"),
#         )
#         item2 = OrderItem.objects.create(
#             order=order,
#             material=self.material2,
#             quantity=Decimal("1.000"),
#             unit_price=Decimal("50.00"),
#         )
#         order.refresh_from_db()
#         self.assertEqual(order.subtotal, Decimal("150.00"))

#         item2.delete()
#         order.refresh_from_db()
#         self.assertEqual(order.subtotal, Decimal("100.00"))
#         self.assertEqual(order.total_amount, Decimal("100.00"))

#     def test_duplicate_material_in_same_order_raises_integrity_error(self):
#         order = Order.objects.create(user=self.user)
#         OrderItem.objects.create(
#             order=order, material=self.material1, quantity=Decimal("1.000")
#         )
#         with self.assertRaises(IntegrityError):
#             OrderItem.objects.create(
#                 order=order, material=self.material1, quantity=Decimal("2.000")
#             )

#     def test_negative_values_raise_validation_error(self):
#         order = Order.objects.create(user=self.user)
#         invalid_item = OrderItem(
#             order=order,
#             material=self.material1,
#             quantity=Decimal("-1.000"),
#         )
#         with self.assertRaises(ValidationError):
#             invalid_item.clean()
