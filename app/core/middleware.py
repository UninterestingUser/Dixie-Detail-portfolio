from django.http import HttpResponseNotFound

# Paths the public entrance (the Cloudflare Tunnel) may reach. Caddy enforces
# the same rule; this is the second check.
PUBLIC_PATHS = ("/health",)
PUBLIC_PREFIXES = ("/api/public/",)


def is_public_path(path):
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


class PublicEntranceMiddleware:
    """Serve only the public paths unless the request came in over the tailnet.

    Caddy sets X-Dixie-Entrance on every request, overwriting any value the
    client sent: "tailnet" on the control-app port, "public" on the tunnel
    port. A request without the header is treated as public.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        entrance = request.headers.get("X-Dixie-Entrance", "public")
        if entrance != "tailnet" and not is_public_path(request.path_info):
            return HttpResponseNotFound()
        return self.get_response(request)
