"""Маршруты выпускников."""

from rest_framework.routers import DefaultRouter

from alumni import views

router = DefaultRouter()
router.register("alumni", views.AlumnusViewSet, basename="alumnus")
router.register("mentorship", views.MentorshipRequestViewSet, basename="mentorship")
router.register("archived-essays", views.ArchivedEssayViewSet, basename="archived-essay")

urlpatterns = router.urls
