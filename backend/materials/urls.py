"""Маршруты раздела материалов."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from materials import views

router = DefaultRouter()
router.register("materials", views.MaterialViewSet, basename="material")
router.register("material-comments", views.MaterialCommentViewSet, basename="material-comment")
router.register("material-reports", views.MaterialReportViewSet, basename="material-report")
router.register("material-requests", views.MaterialRequestViewSet, basename="material-request")
router.register("material-collections", views.MaterialCollectionViewSet, basename="material-collection")

urlpatterns = [
    path("materials/files/<int:pk>/", views.download, name="material-file"),
    path("materials/files/<int:pk>/delete/", views.delete_file, name="material-file-delete"),
    path("olympiad-group/", views.group_list, name="olympiad-group"),
    path("olympiad-group/pick/", views.group_pick, name="olympiad-group-pick"),
    path("materials-state/", views.section_state, name="materials-state"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read/", views.notifications_read, name="notifications-read"),
    *router.urls,
]
