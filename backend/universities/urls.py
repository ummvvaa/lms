"""Маршруты API вузов и соответствия."""

from django.urls import path
from rest_framework.routers import DefaultRouter

from universities import views

router = DefaultRouter()
router.register("universities", views.UniversityViewSet, basename="university")
router.register("programs", views.ProgramViewSet, basename="program")
router.register("rounds", views.AdmissionRoundViewSet, basename="round")
router.register("requirements", views.AdmissionRequirementViewSet, basename="requirement")
router.register("student-universities", views.StudentUniversityViewSet, basename="student-university")

urlpatterns = [
    path("match/my-universities/", views.match_my_universities, name="match-my-universities"),
    path("match/open-programs/", views.match_open_programs, name="match-open-programs"),
    path("match/what-if/", views.match_what_if, name="match-what-if"),
    path("match/list-balance/", views.match_list_balance, name="match-list-balance"),
    path("requirements/import/", views.import_requirements_view, name="requirements-import"),
    *router.urls,
]
