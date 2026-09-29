"""Проверка пароля при входе по почте, логину или подтверждённой личной почте."""

from __future__ import annotations

from django.contrib.auth.backends import ModelBackend

from accounts.logins import find_user


class LoginBackend(ModelBackend):
    """Как `ModelBackend`, только учётная запись ищется `accounts.logins.find_user`.

    Неизвестному идентификатору пароль всё равно хешируется: иначе по
    времени ответа видно, есть ли такой человек.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        user = find_user(username)
        if user is None:
            from accounts.models import User

            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def user_can_authenticate(self, user):
        """Отключённая запись и ученик в архиве — не входят и теряют сессию.

        `get_user` сессии спрашивает то же самое: выпускник, ушедший
        в архив посреди дня, выходит на следующем же запросе.
        """
        from accounts.logins import student_archived

        return super().user_can_authenticate(user) and not student_archived(user)
