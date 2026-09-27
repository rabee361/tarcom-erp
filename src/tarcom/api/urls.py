from rest_framework.routers import DefaultRouter
from .views import *


router = DefaultRouter()
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'otp', OTPViewSet, basename='otp')
router.register(r'users', UserViewSet, basename='users')
router.register(r'materials', MaterialViewSet, basename='materials')
router.register(r'products', MaterialViewSet, basename='products')
router.register(r'categories', MaterialCategoryViewSet, basename='categories')
router.register(r'units', UnitOfMeasureViewSet, basename='units')
router.register(r'uoms', UnitOfMeasureViewSet, basename='uoms')
router.register(r'settings', SettingsViewSet, basename='settings')

urlpatterns = router.urls
