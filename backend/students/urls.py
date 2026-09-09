"""Маршруты API учеников."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from students import admission_views, mock_views, views
from students.notes import CuratorNoteViewSet

router = DefaultRouter()
router.register("students", views.StudentViewSet, basename="student")
router.register("attempts", views.ExamAttemptViewSet, basename="attempt")
router.register("activities", views.ActivityViewSet, basename="activity")
router.register("competitions", views.CompetitionViewSet, basename="competition")
router.register("contacts", views.ParentContactViewSet, basename="contact")
router.register("documents", views.StudentDocumentViewSet, basename="document")
router.register("exam-goals", views.ExamGoalViewSet, basename="exam-goal")
router.register("groups", views.StudyGroupViewSet, basename="group")
# заметки куратора (фаза 62): читают куратор, Кымбат и Салтанат
router.register("notes", CuratorNoteViewSet, basename="note")
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
    path("calendar/", views.calendar_state, name="calendar"),
    path("exam-goals/attention/", views.exam_goals_attention, name="exam-goals-attention"),
    path("portfolio/cv/", views.portfolio_cv, name="portfolio-cv"),
    path("documents/<int:pk>/file/", views.document_file, name="document-file"),
    path("import/preview/", views.import_preview, name="import-preview"),
    path("import/apply/", views.import_apply, name="import-apply"),
    path("enrollment/preview/", views.enrollment_preview, name="enrollment-preview"),
    path("enrollment/apply/", views.enrollment_apply, name="enrollment-apply"),
    path("attempts/bulk/", views.attempts_bulk, name="attempts-bulk"),
    # --- фаза 63: пробники файлом. Шаблон и разбор стоят выше `<int:pk>`,
    # иначе «template» читался бы как номер загрузки ---
    path("mock-imports/", mock_views.mock_imports, name="mock-imports"),
    path("mock-imports/template/", mock_views.mock_template, name="mock-template"),
    path("mock-imports/preview/", mock_views.mock_preview, name="mock-preview"),
    path("mock-imports/apply/", mock_views.mock_apply, name="mock-apply"),
    path("mock-imports/<int:pk>/", mock_views.mock_results, name="mock-results"),
    path("mock-imports/<int:pk>/file/", mock_views.mock_file, name="mock-file"),
    path("mock-imports/<int:pk>/export/", mock_views.mock_export, name="mock-export"),
    path("mock-imports/<int:pk>/archive/", mock_views.mock_archive, name="mock-archive"),
    path("mock-imports/<int:pk>/restore/", mock_views.mock_restore, name="mock-restore"),
    path("mock-imports/<int:pk>/remind/", mock_views.mock_remind, name="mock-remind"),
    # --- фаза 65: пароли ученика и мастер таблицы поступления. Пароль
    # отдаётся только по «показать», и каждый показ пишется в журнал ---
    path("students/<int:pk>/credentials/", admission_views.credentials_state, name="credentials-state"),
    path("students/<int:pk>/credentials/reveal/", admission_views.credential_reveal, name="credential-reveal"),
    path("students/<int:pk>/credentials/set/", admission_views.credential_set, name="credential-set"),
    path("admission-imports/", admission_views.admission_imports, name="admission-imports"),
    path("admission-imports/preview/", admission_views.admission_preview, name="admission-preview"),
    path("admission-imports/apply/", admission_views.admission_apply, name="admission-apply"),
    path("admission-imports/<int:pk>/", admission_views.admission_report, name="admission-report"),
    path("admission-imports/<int:pk>/export/", admission_views.admission_export, name="admission-export"),
    path("competitions/import/preview/", views.competitions_preview, name="competitions-preview"),
    path("competitions/import/apply/", views.competitions_apply, name="competitions-apply"),
    path("contacts/import/preview/", views.contacts_preview, name="contacts-preview"),
    path("contacts/import/apply/", views.contacts_apply, name="contacts-apply"),
    *router.urls,
]
