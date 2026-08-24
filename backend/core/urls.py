"""Маршруты служебного API."""

from django.urls import path

from core import views

urlpatterns = [
    path("meta/domains/", views.domain_meta, name="domain-meta"),
    path("meta/readiness/", views.readiness_config, name="readiness-config"),
    path("dashboards/<str:code>/", views.dashboard, name="dashboard"),
    path("digest/", views.digest, name="digest"),
    path("getting-started/", views.getting_started, name="getting-started"),
    path("search/", views.search_view, name="search"),
    path("mail/status/", views.mail_status, name="mail-status"),
    path("mail/test/", views.mail_test, name="mail-test"),
    path("delete-preview/", views.delete_preview, name="delete-preview"),
    path("archive/", views.archive_list, name="archive"),
    path("archive/<int:pk>/restore/", views.archive_restore, name="archive-restore"),
    path("archive/<int:pk>/purge/", views.archive_purge, name="archive-purge"),
    path("archive/<int:pk>/journal/", views.archive_journal, name="archive-journal"),
    path("archive/cleanup/", views.archive_cleanup, name="archive-cleanup"),
    path("imports/", views.import_batches, name="import-batches"),
    path("imports/<int:pk>/revert/", views.import_batch_revert, name="import-batch-revert"),
]
