
from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('tarcom.api.urls')),
    path('api/', include('tarcom.base.urls')),
    path('silk/', include('silk.urls', namespace='silk')),
]

