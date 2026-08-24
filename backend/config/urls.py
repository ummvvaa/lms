"""Корневые маршруты проекта."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
    path("api/", include("core.urls")),
    path("api/", include("students.urls")),
    path("api/", include("universities.urls")),
    path("api/", include("roadmap.urls")),
    path("api/", include("suggestions.urls")),
    path("api/", include("alumni.urls")),
    path("api/", include("engagement.urls")),
    path("api/", include("prep.urls")),
    path("api/", include("directories.urls")),
    path("api/", include("materials.urls")),
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
