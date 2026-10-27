from django.urls import path

from sport import views

urlpatterns = [
    # директор спорта и администратор: секции, занятия, запись открыта до, выгрузка
    path("sport/sections/", views.sections, name="sport-sections"),
    path("sport/sections/export/", views.sections_export, name="sport-sections-export"),
    path("sport/sections/<int:pk>/", views.section, name="sport-section"),
    path("sport/settings/", views.enroll_settings, name="sport-settings"),
    path("sport/students/", views.student_search, name="sport-student-search"),
    path("sport/enrollments/", views.enrollments, name="sport-enrollments"),
    path("sport/enrollments/<int:pk>/", views.enrollment, name="sport-enrollment"),
    # занятие и QR: директор спорта и администратор показывают код и отмечают вручную
    path("sport/sessions/today/", views.sessions_today, name="sport-sessions-today"),
    path("sport/sessions/<int:pk>/", views.session, name="sport-session"),
    path("sport/sessions/<int:pk>/token/", views.session_token, name="sport-session-token"),
    path("sport/sessions/<int:pk>/end/", views.session_end, name="sport-session-end"),
    path("sport/sessions/<int:pk>/marks/", views.session_mark, name="sport-session-mark"),
    # посещаемость секций: директор спорта, администратор и куратор своих групп
    path("sport/attendance/", views.attendance, name="sport-attendance"),
    path("sport/attendance/export/", views.attendance_export, name="sport-attendance-export"),
    # ученик отсканировал QR — и до входа: код подождёт две минуты
    path("sport/scan/", views.scan, name="sport-scan"),
    # куратор своих групп, директор спорта и администратор: секция ученика на чтение
    path("sport/students/sections/", views.students_sections, name="sport-students-sections"),
    path("sport/students/<int:pk>/section/", views.student_section, name="sport-student-section"),
    # билеты: раздачи у директора спорта и администратора
    path("sport/tickets/", views.ticket_drops, name="sport-tickets"),
    path("sport/tickets/<int:pk>/", views.ticket_drop, name="sport-ticket"),
    path("sport/tickets/<int:pk>/export/", views.ticket_drop_export, name="sport-ticket-export"),
    path("sport/ticket-claims/<int:pk>/missed/", views.ticket_claim_missed, name="sport-ticket-missed"),
    # ученик: раздачи своего класса и свои билеты
    path("my/tickets/", views.my_tickets, name="my-tickets"),
    path("my/tickets/<int:pk>/claim/", views.my_ticket_claim, name="my-ticket-claim"),
    path("my/tickets/<int:pk>/decline/", views.my_ticket_decline, name="my-ticket-decline"),
    path("my/tickets/<int:pk>/accept/", views.my_ticket_accept, name="my-ticket-accept"),
    # ученик: своя секция
    path("my/section/", views.my_section, name="my-section"),
    path("my/section/enroll/", views.my_enroll, name="my-section-enroll"),
    path("my/section/leave/", views.my_leave, name="my-section-leave"),
]
