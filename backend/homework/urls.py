from django.urls import path

from homework import views

urlpatterns = [
    # учитель: ДЗ урока
    path("homework/lessons/<int:pk>/", views.lesson_assignment, name="homework-lesson"),
    # загрузка файла прямо в хранилище по подписанной ссылке
    path("homework/uploads/", views.upload_start, name="homework-upload"),
    path("homework/files/<int:pk>/complete/", views.upload_complete, name="homework-upload-complete"),
    path("homework/files/<int:pk>/", views.file_drop, name="homework-file"),
    path("homework/files/<int:pk>/link/", views.file_link, name="homework-file-link"),
    path("homework/local/<str:token>/", views.local_file, name="homework-local"),
    # ученик
    path("homework/my/", views.my_list, name="homework-my"),
    path("homework/my/<int:pk>/", views.my_detail, name="homework-my-detail"),
    path("homework/my/<int:pk>/submit/", views.my_submit, name="homework-my-submit"),
    # учитель: проверка
    path("homework/review/", views.review_list, name="homework-review"),
    path("homework/review/<int:pk>/", views.review_detail, name="homework-review-detail"),
    path("homework/submissions/<int:pk>/check/", views.review_check, name="homework-check"),
    path("homework/submissions/<int:pk>/zip/", views.review_zip, name="homework-zip"),
    # куратор и руководители
    path("homework/overview/", views.overview, name="homework-overview"),
]
