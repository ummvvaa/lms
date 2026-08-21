"""Маршруты API учеников."""

from rest_framework.routers import DefaultRouter

from students import views

router = DefaultRouter()
router.register("students", views.StudentViewSet, basename="student")
router.register("profiles/behavior", views.BehaviorProfileViewSet, basename="profile-behavior")
router.register("profiles/admission", views.AdmissionProfileViewSet, basename="profile-admission")
router.register("profiles/exam", views.ExamProfileViewSet, basename="profile-exam")
router.register("profiles/talent", views.TalentProfileViewSet, basename="profile-talent")
router.register("profiles/sport", views.SportProfileViewSet, basename="profile-sport")

urlpatterns = router.urls
