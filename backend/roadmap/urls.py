"""Маршруты роадмапа и эссе."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from roadmap import views

router = DefaultRouter()
router.register("tasks", views.TaskViewSet, basename="task")
router.register("task-templates", views.TaskTemplateViewSet, basename="task-template")
router.register("task-comments", views.TaskCommentViewSet, basename="task-comment")
router.register("essays", views.EssayViewSet, basename="essay")
router.register("essay-comments", views.EssayCommentViewSet, basename="essay-comment")

urlpatterns = [
    path("roadmap/generate/", views.generate_roadmap, name="roadmap-generate"),
    *router.urls,
]
