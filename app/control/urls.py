from django.contrib.auth import views as auth_views
from django.urls import path

from . import appointment_views, pricebook_views, staff_views, views

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
    # Jobs.
    path("schedule/", appointment_views.schedule_day, name="schedule"),
    path("schedule/week/", appointment_views.schedule_week, name="schedule-week"),
    path("customers/<int:customer_pk>/appointments/new/", appointment_views.appointment_new, name="appointment-new"),
    path("customers/<int:customer_pk>/appointments/price/", appointment_views.appointment_price, name="appointment-price-new"),
    path("appointments/<int:pk>/", appointment_views.appointment, name="appointment"),
    path("appointments/<int:pk>/edit/", appointment_views.appointment_edit, name="appointment-edit"),
    path("appointments/<int:pk>/price/", appointment_views.appointment_price, name="appointment-price"),
    path("appointments/<int:pk>/status/", appointment_views.appointment_status, name="appointment-status"),
    path("appointments/<int:pk>/final-price/", appointment_views.appointment_final_price, name="appointment-final-price"),
    path("appointments/<int:pk>/staff/", appointment_views.appointment_staff, name="appointment-staff"),
    # Staff and the services they are authorized for.
    path("staff/", staff_views.staff_list, name="staff"),
    path("staff/<int:pk>/", staff_views.staff_member, name="staff-member"),
    path("services/", staff_views.service_list, name="services"),
    path("services/<int:pk>/", staff_views.service, name="service"),
    path("staff/<int:staff_pk>/services/<int:service_pk>/", staff_views.authorization_toggle, name="authorization"),
    # The pricebook.
    path("pricebook/", pricebook_views.pricebook, name="pricebook"),
    path("pricebook/draft/", pricebook_views.pricebook_new_draft, name="pricebook-new-draft"),
    path("pricebook/<int:number>/", pricebook_views.pricebook_version, name="pricebook-version"),
    path("pricebook/<int:number>/save/", pricebook_views.pricebook_save_draft, name="pricebook-save"),
    path("pricebook/<int:number>/discard/", pricebook_views.pricebook_discard_draft, name="pricebook-discard"),
    path("pricebook/<int:number>/publish/", pricebook_views.pricebook_publish, name="pricebook-publish"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("offline/", views.offline, name="offline"),
]
