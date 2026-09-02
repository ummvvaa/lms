"""Маршруты онбординга и геймификации."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from engagement import views

router = DefaultRouter()
# анкета профтеста — справочник директора школы (фаза 45)
router.register("career-questions", views.CareerQuestionViewSet, basename="career-question")
# бейджи — справочник условий, а не код (фаза 46)
router.register("badges", views.BadgeViewSet, basename="badge")
# сюжеты главной и правила обзвона — справочники директора школы (фаза 49)
router.register("home-cues", views.HomeCueViewSet, basename="home-cue")
router.register("call-rules", views.CallRuleViewSet, basename="call-rule")

urlpatterns = [
    path("onboarding/", views.onboarding_state, name="onboarding-state"),
    path("onboarding/answer/", views.onboarding_answer, name="onboarding-answer"),
    path("onboarding/skip/", views.onboarding_skip, name="onboarding-skip"),
    path("onboarding/pending/", views.onboarding_pending, name="onboarding-pending"),
    path("onboarding/pending/<int:pk>/", views.onboarding_review, name="onboarding-review"),
    path("game/me/", views.game_state, name="game-state"),
    path("journey/", views.journey_state, name="journey-state"),
    # --- фаза 49: карусель незакрытых мест на главной ---
    path("home/cues/", views.home_cues, name="home-cues"),
    # --- фаза 47: замки вместо пустоты ---
    path("journey/locks/", views.locks_state, name="journey-locks"),
    # --- фаза 45: профтест ---
    path("career/", views.career_state, name="career-state"),
    path("career/run/", views.career_run, name="career-run"),
    path("career/directions/<int:pk>/agree/", views.career_agree, name="career-agree"),
    # --- фаза 46: достижения ---
    path("achievements/", views.badges_state, name="achievements"),
    *router.urls,
]
