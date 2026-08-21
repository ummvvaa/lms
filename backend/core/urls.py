"""Маршруты служебного API."""

from django.urls import path

from core import views

urlpatterns = [
    path("meta/domains/", views.domain_meta, name="domain-meta"),
]
