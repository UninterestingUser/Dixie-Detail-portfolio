"""The Django admin, for superusers fixing data by hand (decision 0046).
Day-to-day work uses the control app's own screens."""

from django.apps import apps
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

# The apps whose records a superuser may need to fix by hand.
APPS = (
    "customers", "vehicles", "pricebook", "promotions", "appointments",
    "billing", "staff", "bookkeeping", "marketing", "messaging",
)


class SuperuserAdminSite(admin.AdminSite):
    site_header = "Dixie Detail admin"
    site_title = "Dixie Detail admin"
    site_url = "/"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser


def register_all(site):
    """Register every model of APPS, with its change history where it keeps one."""
    for label in APPS:
        for model in apps.get_app_config(label).get_models():
            if model._meta.object_name.startswith("Historical") or site.is_registered(model):
                continue
            history = hasattr(model, "history")
            site.register(model, SimpleHistoryAdmin if history else admin.ModelAdmin)
