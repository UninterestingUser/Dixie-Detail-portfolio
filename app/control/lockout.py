"""Sign-in lockout (decision 0124).

After SIGN_IN_LOCKOUT_FAILURES failed sign-ins for one username, or from
one address, within SIGN_IN_LOCKOUT_WINDOW_MINUTES, sign-ins for that
username or from that address are refused for SIGN_IN_LOCKOUT_MINUTES. Each
lockout is logged, and a manager can clear one.

The address is the client's as Caddy saw it on the tailnet door
(X-Dixie-Client, from Caddy's client_ip). If all that reaches the app is a
proxy's own address on the server (loopback, or Docker's or the LAN's
private ranges), as when tailscale serve passes no client address on, the
address isn't one person's, so only the username limit applies: one
person's typos must not lock everyone out.
"""

import datetime
import ipaddress
import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import SignInFailure, SignInLockout

log = logging.getLogger("control.signin")

PROXY_NETWORKS = [ipaddress.ip_network(net) for net in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7")]


def normal_username(value):
    return (value or "").strip().lower()[:150]


def client_address(request):
    """The client's address, or "" when it isn't known."""
    if request.headers.get("X-Dixie-Entrance") == "tailnet":
        value = request.headers.get("X-Dixie-Client", "").strip() or request.META.get("REMOTE_ADDR", "")
    else:
        value = request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return ""


def personal(address):
    """True when the address can stand for one person: not a proxy's own."""
    if not address:
        return False
    ip = ipaddress.ip_address(address)
    return not any(ip in net for net in PROXY_NETWORKS)


def window_start(now):
    return now - datetime.timedelta(minutes=settings.SIGN_IN_LOCKOUT_WINDOW_MINUTES)


def keys(username, address):
    """The (kind, value) pairs a sign-in attempt is counted and checked by."""
    found = []
    if username:
        found.append((SignInLockout.Kind.USERNAME, username))
    if personal(address):
        found.append((SignInLockout.Kind.ADDRESS, address))
    return found


def active(username, address, now=None):
    """The lockout that applies to this attempt, or None."""
    now = now or timezone.now()
    match = Q(pk__in=[])
    for kind, value in keys(username, address):
        match |= Q(kind=kind, value=value)
    return SignInLockout.objects.filter(match, cleared_at=None, until__gt=now).order_by("-until").first()


def record_failure(username, address, now=None):
    """Note a failed sign-in, and lock out what has failed too often.
    Returns the lockout now in force, if any."""
    now = now or timezone.now()
    SignInFailure.objects.create(username=username, address=address if personal(address) else "", at=now)
    SignInFailure.objects.filter(at__lt=window_start(now)).delete()
    for kind, value in keys(username, address):
        field = "username" if kind == SignInLockout.Kind.USERNAME else "address"
        failures = SignInFailure.objects.filter(**{field: value}, at__gte=window_start(now)).count()
        already = SignInLockout.objects.filter(kind=kind, value=value, cleared_at=None, until__gt=now).exists()
        if failures >= settings.SIGN_IN_LOCKOUT_FAILURES and not already:
            until = now + datetime.timedelta(minutes=settings.SIGN_IN_LOCKOUT_MINUTES)
            SignInLockout.objects.create(kind=kind, value=value, failures=failures, started_at=now, until=until)
            log.warning("Sign-in lockout: %s %s after %d failed sign-ins in %d minutes; refused until %s",
                        kind, value, failures, settings.SIGN_IN_LOCKOUT_WINDOW_MINUTES, until.isoformat(timespec="minutes"))
    return active(username, address, now)


def succeeded(username):
    """A good sign-in clears that username's failures."""
    SignInFailure.objects.filter(username=username).delete()


def clear(lockout, user, now=None):
    """A manager ends a lockout early, with the failures behind it, so the
    next mistake doesn't lock it again at once."""
    now = now or timezone.now()
    lockout.cleared_at = now
    lockout.cleared_by = user
    lockout.save(update_fields=["cleared_at", "cleared_by"])
    field = "username" if lockout.kind == SignInLockout.Kind.USERNAME else "address"
    SignInFailure.objects.filter(**{field: lockout.value}).delete()
    log.warning("Sign-in lockout cleared: %s %s, by %s", lockout.kind, lockout.value, user.get_username())
