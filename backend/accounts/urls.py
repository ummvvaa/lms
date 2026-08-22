"""Маршруты аутентификации."""

from django.urls import path

from accounts import views

urlpatterns = [
    path("auth/entra/", views.entra_login, name="auth-entra"),
    path("auth/local/", views.local_login, name="auth-local"),
    path("auth/magic-link/request/", views.magic_link_request, name="auth-magic-request"),
    path("auth/magic-link/redeem/", views.magic_link_redeem, name="auth-magic-redeem"),
    path("auth/logout/", views.logout_view, name="auth-logout"),
    path("auth/me/", views.me, name="auth-me"),
    path("auth/identities/link/", views.link_identity, name="auth-link-identity"),
]
