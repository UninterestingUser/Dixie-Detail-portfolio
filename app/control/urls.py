from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("sign-in/", auth_views.LoginView.as_view(template_name="control/sign_in.html", redirect_authenticated_user=True), name="sign-in"),
    path("sign-out/", auth_views.LogoutView.as_view(), name="sign-out"),
    path("account/", views.account, name="account"),
    path("customers/", views.customers, name="customers"),
    path("customers/new/", views.customer_form, name="customer-new"),
    path("customers/<int:pk>/", views.customer, name="customer"),
    path("customers/<int:pk>/edit/", views.customer_form, name="customer-edit"),
    path("customers/<int:customer_pk>/vehicles/new/", views.vehicle_form, name="vehicle-new"),
    path("vehicles/<int:pk>/edit/", views.vehicle_form, name="vehicle-edit"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("offline/", views.offline, name="offline"),
]
