from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz),
    # Module APIs mount under /api/v1/ as sprints deliver them.
    path("api/v1/", include("core_hr.urls")),
]
