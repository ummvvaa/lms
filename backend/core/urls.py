"""Маршруты служебного API."""

from django.urls import path

from core import views

urlpatterns = [
    # --- фаза 47: фоновые операции ---
    path("jobs/", views.jobs_list, name="jobs"),
    path("jobs/<int:pk>/dismiss/", views.job_dismiss, name="job-dismiss"),
    path("jobs/<int:pk>/retry/", views.job_retry, name="job-retry"),
    path("meta/domains/", views.domain_meta, name="domain-meta"),
    path("meta/readiness/", views.readiness_config, name="readiness-config"),
    path("dashboards/<str:code>/", views.dashboard, name="dashboard"),
    # --- фаза 49: кабинет руководителя, свой у каждого из шести ---
    path("cabinet/", views.cabinet, name="cabinet"),
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
    path("imports/cleanup/", views.import_history_cleanup, name="import-history-cleanup"),
    path("imports/<int:pk>/revert/", views.import_batch_revert, name="import-batch-revert"),
]
