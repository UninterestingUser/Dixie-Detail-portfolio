from django.contrib import admin
from django.urls import include, path

from core import views
from dixie.admin import register_all

register_all(admin.site)

urlpatterns = [
    path("health", views.health),
    # Superusers only (decision 0046).
    path("admin/", admin.site.urls),
    path("", include("control.urls")),
]
