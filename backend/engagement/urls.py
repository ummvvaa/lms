"""Маршруты онбординга и геймификации."""

from django.urls import path

from engagement import views

urlpatterns = [
    path("onboarding/", views.onboarding_state, name="onboarding-state"),
    path("onboarding/answer/", views.onboarding_answer, name="onboarding-answer"),
    path("onboarding/skip/", views.onboarding_skip, name="onboarding-skip"),
    path("onboarding/pending/", views.onboarding_pending, name="onboarding-pending"),
    path("onboarding/pending/<int:pk>/", views.onboarding_review, name="onboarding-review"),
    path("game/me/", views.game_state, name="game-state"),
]
