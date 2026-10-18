from django.contrib.admin.apps import AdminConfig


class SuperuserAdminConfig(AdminConfig):
    """The Django admin, open to superusers only (decision 0046)."""

    default_site = "dixie.admin.SuperuserAdminSite"
