"""Маршруты онбординга и геймификации."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from engagement import views

router = DefaultRouter()
# анкета профтеста — справочник директора школы (фаза 45)
router.register("career-questions", views.CareerQuestionViewSet, basename="career-question")

urlpatterns = [
    path("onboarding/", views.onboarding_state, name="onboarding-state"),
    path("onboarding/answer/", views.onboarding_answer, name="onboarding-answer"),
    path("onboarding/skip/", views.onboarding_skip, name="onboarding-skip"),
    path("onboarding/pending/", views.onboarding_pending, name="onboarding-pending"),
    path("onboarding/pending/<int:pk>/", views.onboarding_review, name="onboarding-review"),
    path("game/me/", views.game_state, name="game-state"),
    path("journey/", views.journey_state, name="journey-state"),
    # --- фаза 45: профтест ---
    path("career/", views.career_state, name="career-state"),
    path("career/run/", views.career_run, name="career-run"),
    path("career/directions/<int:pk>/agree/", views.career_agree, name="career-agree"),
    *router.urls,
]
