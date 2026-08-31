"""Маршруты API учеников."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from students import views

router = DefaultRouter()
router.register("students", views.StudentViewSet, basename="student")
router.register("attempts", views.ExamAttemptViewSet, basename="attempt")
router.register("activities", views.ActivityViewSet, basename="activity")
router.register("competitions", views.CompetitionViewSet, basename="competition")
router.register("contacts", views.ParentContactViewSet, basename="contact")
router.register("documents", views.StudentDocumentViewSet, basename="document")
router.register("groups", views.StudyGroupViewSet, basename="group")
router.register("profiles/behavior", views.BehaviorProfileViewSet, basename="profile-behavior")
router.register("profiles/admission", views.AdmissionProfileViewSet, basename="profile-admission")
router.register("profiles/exam", views.ExamProfileViewSet, basename="profile-exam")
router.register("profiles/talent", views.TalentProfileViewSet, basename="profile-talent")
router.register("profiles/sport", views.SportProfileViewSet, basename="profile-sport")

urlpatterns = [
    path("batch/save/", views.batch_save, name="batch-save"),
    # --- фаза 38: портфолио. Файл документа — своим маршрутом с проверкой
    # прав; он стоит выше роутера, иначе `file` читался бы как действие ---
    path("portfolio/", views.portfolio_state, name="portfolio"),
    path("portfolio/cv/", views.portfolio_cv, name="portfolio-cv"),
    path("documents/<int:pk>/file/", views.document_file, name="document-file"),
    path("import/preview/", views.import_preview, name="import-preview"),
    path("import/apply/", views.import_apply, name="import-apply"),
    path("enrollment/preview/", views.enrollment_preview, name="enrollment-preview"),
    path("enrollment/apply/", views.enrollment_apply, name="enrollment-apply"),
    path("attempts/bulk/", views.attempts_bulk, name="attempts-bulk"),
    path("competitions/import/preview/", views.competitions_preview, name="competitions-preview"),
    path("competitions/import/apply/", views.competitions_apply, name="competitions-apply"),
    path("contacts/import/preview/", views.contacts_preview, name="contacts-preview"),
    path("contacts/import/apply/", views.contacts_apply, name="contacts-apply"),
    *router.urls,
]
