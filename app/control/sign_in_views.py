"""Signing in, with the lockout (decision 0124), and the managers' screen
for clearing a lockout."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from staff.authorization import user_is_manager

from . import lockout
from .models import SignInLockout


class SignInView(auth_views.LoginView):
    template_name = "control/sign_in.html"
    redirect_authenticated_user = True

    def attempt(self):
        return lockout.normal_username(self.request.POST.get("username")), lockout.client_address(self.request)

    def locked(self, form):
        context = self.get_context_data(form=form, locked=True, lockout_minutes=settings.SIGN_IN_LOCKOUT_MINUTES)
        return self.render_to_response(context, status=429)

    def post(self, request, *args, **kwargs):
        username, address = self.attempt()
        if lockout.active(username, address):
            # Refused before the password is checked at all: an unbound
            # form, since showing a bound one would validate it, and
            # validating checks the password.
            return self.locked(self.form_class(request, initial={"username": request.POST.get("username", "")}))
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        username, address = self.attempt()
        if lockout.record_failure(username, address):
            return self.locked(form)
        return super().form_invalid(form)

    def form_valid(self, form):
        lockout.succeeded(lockout.normal_username(form.get_user().get_username()))
        return super().form_valid(form)


def sign_in_lockouts(request):
    if not user_is_manager(request.user):
        return HttpResponseForbidden("Only a manager can see sign-in lockouts.")
    now = timezone.now()
    return render(request, "control/sign_in_lockouts.html", {
        "active": SignInLockout.objects.filter(cleared_at=None, until__gt=now),
        "recent": SignInLockout.objects.exclude(cleared_at=None, until__gt=now)[:20],
        "settings_failures": settings.SIGN_IN_LOCKOUT_FAILURES,
        "settings_window": settings.SIGN_IN_LOCKOUT_WINDOW_MINUTES,
        "settings_minutes": settings.SIGN_IN_LOCKOUT_MINUTES,
    })


@require_POST
def sign_in_lockout_clear(request, pk):
    if not user_is_manager(request.user):
        return HttpResponseForbidden("Only a manager can clear a sign-in lockout.")
    found = get_object_or_404(SignInLockout, pk=pk, cleared_at=None)
    lockout.clear(found, request.user)
    messages.success(request, f"Cleared: sign-ins for {found.value} are allowed again.")
    return redirect("sign-in-lockouts")
