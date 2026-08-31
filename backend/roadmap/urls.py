"""Маршруты роадмапа и эссе."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from roadmap import views

router = DefaultRouter()
router.register("tasks", views.TaskViewSet, basename="task")
router.register("task-templates", views.TaskTemplateViewSet, basename="task-template")
router.register("task-comments", views.TaskCommentViewSet, basename="task-comment")
router.register("application-plans", views.ApplicationPlanViewSet, basename="application-plan")
router.register("essays", views.EssayViewSet, basename="essay")
router.register("essay-comments", views.EssayCommentViewSet, basename="essay-comment")

urlpatterns = [
    path("roadmap/generate/", views.generate_roadmap, name="roadmap-generate"),
    path("application-plans/attention/", views.plan_attention, name="plan-attention"),
    *router.urls,
]
