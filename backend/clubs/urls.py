from django.urls import path

from clubs import admin_views

urlpatterns = [
    # администратор: кружки, правка, архив, записанные и выгрузка
    path("clubs/", admin_views.clubs, name="clubs-list"),
    path("clubs/mentors/", admin_views.mentors, name="clubs-mentors"),
    path("clubs/<int:pk>/", admin_views.club, name="clubs-club"),
    path("clubs/<int:pk>/members/", admin_views.members, name="clubs-members"),
    path("clubs/<int:pk>/members/export/", admin_views.members_export, name="clubs-members-export"),
]
