from django.urls import path

from directors import views

urlpatterns = [
    # директор школы: обзвон и история звонков
    path("directors/calls/today/", views.calls_today, name="cabinet-calls-today"),
    path("directors/calls/", views.calls, name="cabinet-calls"),
    path("directors/calls/export/", views.calls_export, name="cabinet-calls-export"),
    # отчёты одного места: директор школы и академический директор
    path("directors/reports/", views.report_list, name="cabinet-reports"),
    path("directors/reports/parent-groups/", views.report_groups, name="cabinet-report-groups"),
    path("directors/reports/<slug:kind>/", views.report_detail, name="cabinet-report"),
    path("directors/reports/<slug:kind>/export/", views.report_export, name="cabinet-report-export"),
    path("directors/reports/<slug:kind>/seen/", views.report_seen, name="cabinet-report-seen"),
    # задачи сотрудникам: ставит Кымбат, отмечает исполнитель у себя на главной
    path("directors/staff-tasks/", views.staff_tasks, name="staff-tasks"),
    path("directors/staff-tasks/people/", views.staff_task_people, name="staff-task-people"),
    path("directors/staff-tasks/mine/", views.my_staff_tasks, name="staff-tasks-mine"),
    path("directors/staff-tasks/<int:pk>/", views.staff_task, name="staff-task"),
    path("directors/staff-tasks/<int:pk>/done/", views.my_staff_task_done, name="staff-task-done"),
    # результаты экзаменов 11 у Кымбат — на чтение
    path("directors/exam-results/", views.exam_results, name="exam-results"),
    path("directors/exam-results/export/", views.exam_results_export, name="exam-results-export"),
    path("directors/exam-results/<int:pk>/", views.exam_results_student, name="exam-results-student"),
    # эссе учеников у Асем
    path("directors/essays/", views.essay_review, name="essay-review"),
    path("directors/essays/<int:pk>/", views.essay_review_detail, name="essay-review-detail"),
    path("directors/essays/<int:pk>/verdict/", views.essay_review_verdict, name="essay-review-verdict"),
    # олимпиады и освобождения у Армана
    path("directors/olympiads/", views.olympiads, name="olympiad-events"),
    path("directors/olympiads/<int:pk>/", views.olympiad, name="olympiad-event"),
    path("directors/olympiads/<int:pk>/entries/", views.olympiad_entries, name="olympiad-event-entries"),
    path("directors/olympiad-entries/<int:pk>/", views.olympiad_entry, name="olympiad-event-entry"),
    path("directors/releases/", views.releases, name="lesson-releases"),
    path("directors/releases/<int:pk>/", views.release, name="lesson-release"),
    # мероприятия и заявки у Нурлыбека
    path("directors/sport-events/", views.sport_events, name="sport-events"),
    path("directors/sport-events/applications/", views.sport_applications, name="sport-applications"),
    path("directors/sport-events/<int:pk>/", views.sport_event, name="sport-event"),
    path(
        "directors/sport-events/<int:pk>/applications/", views.sport_event_applications, name="sport-event-applications"
    ),
    path("directors/sport-events/<int:pk>/export/", views.sport_event_export, name="sport-event-export"),
    path("directors/sport-applications/<int:pk>/", views.sport_application, name="sport-application"),
    path(
        "directors/sport-applications/<int:pk>/release/",
        views.sport_application_release,
        name="sport-application-release",
    ),
    # ученик: «Спорт» — мероприятия и свои заявки
    path("my/sport-events/", views.my_sport, name="my-sport-events"),
    path("my/sport-events/<int:pk>/apply/", views.my_sport_apply, name="my-sport-apply"),
    path("my/sport-applications/<int:pk>/", views.my_sport_application, name="my-sport-application"),
]
