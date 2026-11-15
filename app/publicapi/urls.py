"""The public API, version 1. Caddy's public port and the app's own
entrance check let only /health and /api/public/ through from the internet
(decision 0038)."""

from django.urls import path

from . import views

urlpatterns = [
    path("services", views.services, name="api-services"),
    path("booking-options", views.booking_options, name="api-booking-options"),
    path("price-table", views.price_table, name="api-price-table"),
    path("vehicles/years", views.vehicle_years, name="api-vehicle-years"),
    path("vehicles/makes", views.vehicle_makes, name="api-vehicle-makes"),
    path("vehicles/models", views.vehicle_models, name="api-vehicle-models"),
    path("vehicles/lookup", views.vehicle_lookup, name="api-vehicle-lookup"),
    path("vehicles/photo-cards", views.photo_cards, name="api-photo-cards"),
    path("addresses", views.addresses, name="api-addresses"),
    path("quotes", views.create_quote, name="api-quotes"),
    path("open-times", views.open_times, name="api-open-times"),
    path("bookings", views.create_booking, name="api-bookings"),
    path("quote-requests/uploads", views.upload_session, name="api-upload-session"),
    path("quote-requests/uploads/<str:session>/photos", views.upload_photo, name="api-upload-photo"),
    path("quote-requests/uploads/<str:session>/photos/<str:photo>", views.delete_photo, name="api-delete-photo"),
    path("quote-requests/offline", views.create_offline_quote_request, name="api-offline-quote-requests"),
    path("quote-requests", views.create_quote_request, name="api-quote-requests"),
    path("time-requests", views.create_time_request, name="api-time-requests"),
]
