"""Маршруты движка предложений."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from suggestions import views

router = DefaultRouter()
router.register("suggestions", views.SuggestionViewSet, basename="suggestion")

urlpatterns = [
    path("commands/", views.available_commands, name="commands"),
    path("commands/paste/", views.paste, name="command-paste"),
    path("commands/upload/", views.upload, name="command-upload"),
    path("commands/explain-match/", views.explain_match, name="command-explain-match"),
    path("commands/essay-questions/", views.essay_questions, name="command-essay-questions"),
    # --- фаза 20: операции с моделью ---
    path("commands/run/", views.run_operation, name="command-run"),
    path("commands/parse-university/", views.parse_university, name="command-parse-university"),
    path("commands/parse-activity/", views.parse_activity, name="command-parse-activity"),
    path("commands/verify-requirements/", views.verify_requirements, name="command-verify-requirements"),
    path("commands/parse-image/", views.parse_image, name="command-parse-image"),
    path("assistant/quick/", views.assistant_quick, name="assistant-quick"),
    path("assistant/threads/", views.assistant_threads, name="assistant-threads"),
    path("assistant/threads/<int:pk>/", views.assistant_thread_detail, name="assistant-thread"),
    path("assistant/ask/", views.assistant_ask, name="assistant-ask"),
    path("llm/status/", views.llm_status, name="llm-status"),
    path("llm/spend/", views.llm_spend, name="llm-spend"),
    path("tasks/status/<str:task_id>/", views.task_status, name="task-status"),
    *router.urls,
]
