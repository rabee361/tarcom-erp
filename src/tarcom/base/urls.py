from django.urls import path
from .views.auth import *
from .views.core import *

urlpatterns = [
    path("login/", DashboardLoginView.as_view(), name="login"),
    path("logout/", DashboardLogoutView.as_view(), name="logout"),
    path("change-password/", DashboardChangePasswordView.as_view(), name="change-password"),

    path("", DashboardView.as_view(), name="home"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/partial/", DashboardPartialView.as_view(), name="dashboard-partial"),

    path("dashboard/users/", UsersListView.as_view(), name="users-list"),
    path("dashboard/users/create/", UserCreateView.as_view(), name="user-create"),
    path("dashboard/users/<int:pk>/edit/", UserUpdateView.as_view(), name="user-edit"),
    path("dashboard/users/<int:pk>/delete/", UserDeleteView.as_view(), name="user-delete"),

    path("dashboard/materials/", MaterialListView.as_view(), name="materials-list"),
    path("dashboard/materials/create/", MaterialCreateView.as_view(), name="material-create"),
    path("dashboard/materials/<int:pk>/edit/", MaterialUpdateView.as_view(), name="material-edit"),
    path("dashboard/materials/<int:pk>/delete/", MaterialDeleteView.as_view(), name="material-delete"),

    path("dashboard/categories/", CategoryListView.as_view(), name="categories-list"),
    path("dashboard/categories/create/", CategoryCreateView.as_view(), name="category-create"),
    path("dashboard/categories/<int:pk>/edit/", CategoryUpdateView.as_view(), name="category-edit"),
    path("dashboard/categories/<int:pk>/delete/", CategoryDeleteView.as_view(), name="category-delete"),

    path("dashboard/units/", UnitListView.as_view(), name="units-list"),
    path("dashboard/units/create/", UnitCreateView.as_view(), name="unit-create"),
    path("dashboard/units/<int:pk>/edit/", UnitUpdateView.as_view(), name="unit-edit"),
    path("dashboard/units/<int:pk>/delete/", UnitDeleteView.as_view(), name="unit-delete"),

    path("dashboard/orders/", OrderListView.as_view(), name="orders-list"),
    path("dashboard/orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("dashboard/orders/<int:pk>/status/", OrderStatusUpdateView.as_view(), name="order-status-update"),
]
