"""Маршруты служебного API."""

from django.urls import path

from core import curator, views

urlpatterns = [
    # --- фаза 47: фоновые операции ---
    path("jobs/", views.jobs_list, name="jobs"),
    path("jobs/<int:pk>/dismiss/", views.job_dismiss, name="job-dismiss"),
    path("jobs/<int:pk>/retry/", views.job_retry, name="job-retry"),
    path("meta/domains/", views.domain_meta, name="domain-meta"),
    # кабинет куратора (фаза 61): главная, ученики, карточка, задачи
    path("curator/overview/", curator.overview, name="curator-overview"),
    path("curator/students/", curator.students_list, name="curator-students"),
    path("curator/students/export/", curator.students_export, name="curator-students-export"),
    path("curator/students/<int:pk>/", curator.student_card, name="curator-student"),
    path("curator/tasks/", curator.tasks, name="curator-tasks"),
    path("curator/tasks/<int:pk>/status/", curator.task_status, name="curator-task-status"),
    path("curator/profile/", curator.profile, name="curator-profile"),
    # документы, звонок, передача, журнал (фаза 62)
    path("curator/documents/", curator.documents_matrix, name="curator-documents"),
    path("curator/documents/export/", curator.documents_export, name="curator-documents-export"),
    path("curator/documents/remind/", curator.documents_remind, name="curator-documents-remind"),
    path("curator/documents/<int:pk>/revoke/", curator.document_revoke, name="curator-document-revoke"),
    path("curator/students/<int:pk>/call/", curator.parent_call, name="curator-call"),
    path("curator/students/<int:pk>/escalate/", curator.escalate_student, name="curator-escalate"),
    path("curator/journal/", curator.journal, name="curator-journal"),
    path("curator/journal/export/", curator.journal_export, name="curator-journal-export"),
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
