"""Маршруты справочников."""

from rest_framework.routers import DefaultRouter

from directories import views

router = DefaultRouter()
router.register("subjects", views.OlympiadSubjectViewSet, basename="subject")
router.register("sport-types", views.SportTypeViewSet, basename="sport-type")

urlpatterns = router.urls
