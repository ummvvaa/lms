"""Маршруты профтеста. Имена — в списках шлюзов куратора и учителя и в реестре параллелей."""

from django.urls import path

from career import views

urlpatterns = [
    # --- учитель профориентации, администратор, читатели результатов ---
    path("career/tests/", views.tests, name="career-tests"),
    path("career/tests/preview/", views.test_preview, name="career-test-preview"),
    path("career/tests/template/", views.test_template, name="career-test-template"),
    path("career/tests/<int:pk>/", views.test_detail, name="career-test"),
    path("career/tests/<int:pk>/file/", views.test_file, name="career-test-file"),
    path("career/tests/<int:pk>/assignments/", views.test_assignments, name="career-test-assignments"),
    path("career/groups/", views.groups, name="career-groups"),
    path("career/results/", views.results, name="career-results"),
    path("career/attempts/<int:pk>/", views.attempt_detail, name="career-attempt"),
    path("career/attempts/<int:pk>/retake/", views.attempt_retake, name="career-attempt-retake"),
    path("career/analyses/", views.analyses_view, name="career-analyses"),
    path("career/analyses/<int:pk>/", views.analysis_detail, name="career-analysis"),
    path("career/students/<int:pk>/", views.student_results, name="career-student"),
    # --- ученик ---
    path("career/my/", views.my, name="career-my"),
    path("career/my/tests/<int:pk>/start/", views.my_start, name="career-my-start"),
    path("career/my/attempts/<int:pk>/", views.my_attempt, name="career-my-attempt"),
    path("career/my/attempts/<int:pk>/answers/", views.my_answers, name="career-my-answers"),
    path("career/my/attempts/<int:pk>/finish/", views.my_finish, name="career-my-finish"),
]
