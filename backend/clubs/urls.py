from django.urls import path

from clubs import admin_views, mentor_views, student_views

urlpatterns = [
    # администратор: кружки, правка, архив, записанные и выгрузка
    path("clubs/", admin_views.clubs, name="clubs-list"),
    path("clubs/mentors/", admin_views.mentors, name="clubs-mentors"),
    path("clubs/<int:pk>/", admin_views.club, name="clubs-club"),
    path("clubs/<int:pk>/members/", admin_views.members, name="clubs-members"),
    path("clubs/<int:pk>/members/export/", admin_views.members_export, name="clubs-members-export"),
    # ментор своего кружка и администратор: ученики, задание, отметка, заметки
    path("clubs/mine/", mentor_views.mine, name="clubs-mentor"),
    path("clubs/<int:pk>/students/", mentor_views.students, name="clubs-mentor-club"),
    path("clubs/<int:pk>/homework/", mentor_views.homework, name="clubs-homework"),
    path("clubs/<int:pk>/homework/<int:hw>/", mentor_views.homework_detail, name="clubs-homework-detail"),
    path("clubs/homework/<int:hw>/file/", mentor_views.homework_file, name="clubs-homework-file"),
    path("clubs/<int:pk>/session/", mentor_views.session, name="clubs-session"),
    path("clubs/<int:pk>/session/token/", mentor_views.session_token, name="clubs-session-token"),
    path("clubs/<int:pk>/session/marks/", mentor_views.session_mark, name="clubs-session-mark"),
    path("clubs/<int:pk>/notes/", mentor_views.notes, name="clubs-notes"),
    path("clubs/notes/<int:pk>/", mentor_views.note, name="clubs-note"),
    # ученик отсканировал QR встречи — и до входа: код подождёт, как у секций
    path("clubs/scan/", mentor_views.scan, name="clubs-scan"),
    # ученик: свои кружки, запись и выход
    path("my/clubs/", student_views.my_clubs, name="my-clubs"),
    path("my/clubs/<int:pk>/enroll/", student_views.my_enroll, name="my-club-enroll"),
    path("my/clubs/<int:pk>/leave/", student_views.my_leave, name="my-club-leave"),
]
