"""Маршруты служебного API."""

from django.urls import path

from core import views

urlpatterns = [
    path("meta/domains/", views.domain_meta, name="domain-meta"),
    path("meta/readiness/", views.readiness_config, name="readiness-config"),
    path("dashboards/<str:code>/", views.dashboard, name="dashboard"),
    path("digest/", views.digest, name="digest"),
    path("delete-preview/", views.delete_preview, name="delete-preview"),
    path("archive/", views.archive_list, name="archive"),
    path("archive/<int:pk>/restore/", views.archive_restore, name="archive-restore"),
    path("imports/", views.import_batches, name="import-batches"),
    path("imports/<int:pk>/revert/", views.import_batch_revert, name="import-batch-revert"),
]
