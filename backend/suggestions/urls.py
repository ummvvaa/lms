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
    path("tasks/status/<str:task_id>/", views.task_status, name="task-status"),
    *router.urls,
]
