"""Маршруты аутентификации и управления учётными записями."""

from django.urls import path

from accounts import views

urlpatterns = [
    path("auth/login/", views.login_view, name="auth-login"),
    path("auth/logout/", views.logout_view, name="auth-logout"),
    path("auth/me/", views.me, name="auth-me"),
    path("auth/me/preferences/", views.preferences, name="auth-preferences"),
    path("auth/password/change/", views.password_change, name="auth-password-change"),
    path("auth/password/reset/", views.password_reset_request, name="auth-password-reset"),
    path("auth/password/set/", views.password_reset_confirm, name="auth-password-set"),
    path("auth/magic-link/request/", views.magic_link_request, name="auth-magic-request"),
    path("auth/magic-link/redeem/", views.magic_link_redeem, name="auth-magic-redeem"),
    path("auth/identities/link/", views.link_identity, name="auth-link-identity"),
    path("users/", views.users, name="users"),
    path("users/invite/", views.invite, name="users-invite"),
    path("users/<int:pk>/", views.user_detail, name="user-detail"),
    path("users/<int:pk>/invite-link/", views.user_invite_link, name="user-invite-link"),
]
