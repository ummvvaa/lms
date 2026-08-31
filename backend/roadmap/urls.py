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
router.register("essay-doc-types", views.EssayDocTypeViewSet, basename="essay-doc-type")
router.register("essay-guides", views.EssayGuideViewSet, basename="essay-guide")
router.register("essay-checks", views.EssayCheckQuestionViewSet, basename="essay-check")
router.register("essay-examples", views.EssayExampleViewSet, basename="essay-example")

urlpatterns = [
    path("roadmap/generate/", views.generate_roadmap, name="roadmap-generate"),
    path("application-plans/attention/", views.plan_attention, name="plan-attention"),
    path("essays/reading-of-the-day/", views.reading_of_the_day, name="essay-reading-day"),
    path("essays/requirements/", views.essay_requirements, name="essay-requirements"),
    path("essays/<int:pk>/assist-log/", views.essay_assist_log, name="essay-assist-log"),
    *router.urls,
]
