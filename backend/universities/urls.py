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
    path("match/at-goal/", views.match_at_goal, name="match-at-goal"),
    path("match/list-balance/", views.match_list_balance, name="match-list-balance"),
    # --- фаза 40: подбор с историей и избранное ---
    path("selection/runs/", views.selection_runs, name="selection-runs"),
    path("selection/runs/start/", views.selection_start, name="selection-start"),
    path("selection/runs/active/", views.selection_active, name="selection-active"),
    path("selection/runs/<int:pk>/", views.selection_run_detail, name="selection-run"),
    path("selection/runs/<int:pk>/explain/<int:program_id>/", views.selection_explain, name="selection-explain"),
    path("favorites/", views.favorites_view, name="favorites"),
    path("favorites/program/<int:program_id>/", views.favorite_remove, name="favorite-remove"),
    path("catalog/", views.catalog, name="catalog"),
    path("catalog/facets/", views.catalog_facets, name="catalog-facets"),
    path("catalog/add/", views.add_to_my_list, name="catalog-add"),
    path("catalog/remove/<int:pk>/", views.remove_from_my_list, name="catalog-remove"),
    path("catalog/pick/", views.catalog_pick, name="catalog-pick"),
    path("catalog/pending/", views.pending_additions, name="catalog-pending"),
    path("catalog/pending/<int:pk>/", views.review_addition, name="catalog-review"),
    path("requirements/import/", views.import_requirements_view, name="requirements-import"),
    path("catalog/seed/", views.seed_catalog_view, name="catalog-seed"),
    path("catalog/verify/", views.verify_record, name="catalog-verify"),
    *router.urls,
]
