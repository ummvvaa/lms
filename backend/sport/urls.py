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
    # куратор своих групп, директор спорта и администратор: секция ученика на чтение
    path("sport/students/sections/", views.students_sections, name="sport-students-sections"),
    path("sport/students/<int:pk>/section/", views.student_section, name="sport-student-section"),
    # ученик: своя секция
    path("my/section/", views.my_section, name="my-section"),
    path("my/section/enroll/", views.my_enroll, name="my-section-enroll"),
    path("my/section/leave/", views.my_leave, name="my-section-leave"),
]
