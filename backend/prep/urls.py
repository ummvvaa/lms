"""Маршруты центра подготовки."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from prep import views

router = DefaultRouter()
router.register("prep/questions", views.QuestionViewSet, basename="prep-question")
router.register("prep/mocks", views.MockExamViewSet, basename="prep-mock")

urlpatterns = [
    path("prep/questions/import/", views.questions_import, name="prep-questions-import"),
    path("prep/bank/", views.bank_overview, name="prep-bank"),
    path("prep/practice/start/", views.practice_start, name="prep-practice-start"),
    path("prep/practice/<int:pk>/", views.practice_detail, name="prep-practice-detail"),
    path("prep/practice/<int:pk>/answer/", views.practice_answer, name="prep-practice-answer"),
    path("prep/practice/<int:pk>/finish/", views.practice_finish, name="prep-practice-finish"),
    path("prep/mocks/<int:pk>/start/", views.mock_start, name="prep-mock-start"),
    path("prep/runs/my/", views.my_runs, name="prep-my-runs"),
    path("prep/runs/platform/", views.platform_mocks, name="prep-platform-mocks"),
    path("prep/runs/<int:pk>/review/", views.review_platform_mock, name="prep-review-mock"),
    *router.urls,
]
