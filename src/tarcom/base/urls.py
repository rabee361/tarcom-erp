from django.urls import path
from .views import *


urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/partial/", DashboardPartialView.as_view(), name="dashboard-partial"),
]