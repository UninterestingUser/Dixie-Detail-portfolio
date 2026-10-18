from django.contrib.auth.decorators import login_not_required
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_safe


@login_not_required
@require_safe
def health(request):
    """Report whether the app is up and can reach the database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
