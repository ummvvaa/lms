"""Маршруты служебного API."""

from django.urls import path

from core import views

urlpatterns = [
    path("meta/domains/", views.domain_meta, name="domain-meta"),
    path("meta/readiness/", views.readiness_config, name="readiness-config"),
    path("dashboards/<str:code>/", views.dashboard, name="dashboard"),
]
