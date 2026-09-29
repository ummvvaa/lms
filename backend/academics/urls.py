"""Маршруты учебной части. Имена `acad-*` читают шлюзы ролей."""

from django.urls import path

from academics import report_views, schedule_views, teacher_views, views

urlpatterns = [
    path("acad/meta/", views.meta, name="acad-meta"),
    # уроки
    path("acad/lessons/", views.lessons, name="acad-lessons"),
    path("acad/lessons/<int:pk>/", views.lesson_detail, name="acad-lesson"),
    path("acad/lessons/<int:pk>/attendance/", views.lesson_attendance, name="acad-lesson-attendance"),
    path("acad/lessons/<int:pk>/grade/", views.lesson_grade, name="acad-lesson-grade"),
    path("acad/lessons/<int:pk>/meta/", views.lesson_meta, name="acad-lesson-meta"),
    path("acad/lessons/<int:pk>/remind/", views.lesson_remind, name="acad-lesson-remind"),
    path("acad/lessons/<int:pk>/edit/", schedule_views.lesson_edit, name="acad-lesson-edit"),
    path("acad/lessons/<int:pk>/substitute/", schedule_views.lesson_substitute, name="acad-lesson-substitute"),
    path("acad/lessons/<int:pk>/move/", schedule_views.lesson_move, name="acad-lesson-move"),
    path("acad/lessons/<int:pk>/cancel/", schedule_views.lesson_cancel, name="acad-lesson-cancel"),
    path("acad/lessons/<int:pk>/restore/", schedule_views.lesson_restore, name="acad-lesson-restore"),
    path("acad/lessons/<int:pk>/delete/", schedule_views.lesson_delete, name="acad-lesson-delete"),
    path("acad/conflicts/", schedule_views.conflicts_check, name="acad-conflicts"),
    path("acad/schedule/", schedule_views.schedule_week, name="acad-schedule"),
    path("acad/schedule/import/preview/", schedule_views.schedule_import_preview, name="acad-schedule-import-preview"),
    path("acad/schedule/import/apply/", schedule_views.schedule_import_apply, name="acad-schedule-import-apply"),
    # кабинет учителя
    path("acad/teacher/today/", teacher_views.today_screen, name="acad-teacher-today"),
    path("acad/teacher/journals/", teacher_views.journals, name="acad-teacher-journals"),
    path("acad/teacher/profile/", teacher_views.profile, name="acad-teacher-profile"),
    path("acad/teacher/students/<int:pk>/", teacher_views.student_view, name="acad-teacher-student"),
    path("acad/journals/<int:pk>/", teacher_views.journal, name="acad-journal"),
    path("acad/journals/<int:pk>/export/", teacher_views.journal_export, name="acad-journal-export"),
    path("acad/journals/<int:pk>/final/", teacher_views.journal_final, name="acad-journal-final"),
    path("acad/journals/<int:pk>/reassign/", schedule_views.course_reassign, name="acad-course-reassign"),
    path("acad/requests/", views.requests, name="acad-requests"),
    path("acad/requests/<int:pk>/decide/", views.request_decide, name="acad-request-decide"),
    # составы и учителя
    path("acad/cohorts/", schedule_views.cohorts, name="acad-cohorts"),
    path("acad/cohorts/all/", schedule_views.group_cohorts, name="acad-cohorts-all"),
    path("acad/cohorts/split/", schedule_views.cohort_split, name="acad-cohort-split"),
    path("acad/cohorts/stream/", schedule_views.cohort_stream, name="acad-cohort-stream"),
    path("acad/cohorts/<int:pk>/", schedule_views.cohort, name="acad-cohort"),
    path("acad/teachers/", schedule_views.teachers_list, name="acad-teachers"),
    path("acad/teachers/remind-all/", schedule_views.teachers_remind_all, name="acad-teachers-remind-all"),
    path("acad/teachers/<int:pk>/", schedule_views.teacher_detail, name="acad-teacher"),
    path("acad/teachers/<int:pk>/remind/", schedule_views.teacher_remind, name="acad-teacher-remind"),
    # успеваемость
    path("acad/grades/school/", schedule_views.school_grades, name="acad-school-grades"),
    path("acad/grades/school/cell/", schedule_views.school_grades_cell, name="acad-school-grades-cell"),
    path("acad/grades/school/export/", schedule_views.school_grades_export, name="acad-school-grades-export"),
    path("acad/grades/group/", schedule_views.group_grades, name="acad-group-grades"),
    path("acad/grades/group/export/", schedule_views.group_grades_export, name="acad-group-grades-export"),
    path("acad/students/<int:pk>/grades/", views.student_grades, name="acad-student-grades"),
    path("acad/me/grades/", views.my_grades, name="acad-my-grades"),
    path("acad/me/lessons/", views.my_lessons, name="acad-my-lessons"),
    path("acad/me/home/", views.my_home, name="acad-my-home"),
    # посещаемость по урокам, причины, риски
    path("acad/attendance/", views.attendance, name="acad-attendance"),
    path("acad/attendance/export/", views.attendance_export, name="acad-attendance-export"),
    path("acad/excuses/", views.excuses, name="acad-excuses"),
    path("acad/excuses/<int:pk>/", views.excuse_drop, name="acad-excuse"),
    path("acad/excuses/<int:pk>/file/", views.excuse_file, name="acad-excuse-file"),
    path("acad/risks/", views.risks, name="acad-risks"),
    # учебный год
    path("acad/year/", schedule_views.year, name="acad-year"),
    path("acad/year/quarters/<int:pk>/close/", schedule_views.quarter_close, name="acad-quarter-close"),
    # отчёты родителям
    path("acad/reports/", report_views.reports, name="acad-reports"),
    path("acad/reports/build/", report_views.reports_build, name="acad-reports-build"),
    path("acad/reports/zip/", report_views.reports_zip, name="acad-reports-zip"),
    path("acad/reports/sent/", report_views.reports_sent, name="acad-reports-sent"),
    path("acad/reports/check/", report_views.reports_check, name="acad-reports-check"),
    path("acad/reports/refresh/", report_views.reports_refresh, name="acad-reports-refresh"),
    path("acad/reports/<int:pk>/", report_views.report, name="acad-report"),
    path("acad/reports/<int:pk>/check/", report_views.report_check, name="acad-report-check"),
    path("acad/reports/<int:pk>/refresh/", report_views.report_refresh, name="acad-report-refresh"),
    path("acad/reports/<int:pk>/pdf/", report_views.report_pdf, name="acad-report-pdf"),
    path("acad/reports/<int:pk>/sent/", report_views.report_sent, name="acad-report-sent"),
    # блоки главных
    path("acad/curator/home/", views.curator_home, name="acad-curator-home"),
    path("acad/dashboard/", views.dashboard_block, name="acad-dashboard"),
]
