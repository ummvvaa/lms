"""Сериализаторы аутентификации и текущего пользователя."""

from __future__ import annotations

from rest_framework import serializers

from accounts.models import Identity, Language, Role, Theme, User
from accounts.naming import NameRejected, check_full_name
from core.domains import DOMAINS, ROLE_TITLES


class IdentitySerializer(serializers.ModelSerializer):
    provider_title = serializers.CharField(source="get_provider_display", read_only=True)

    class Meta:
        model = Identity
        fields = ("id", "provider", "provider_title", "email", "is_primary", "last_login_at")
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer):
    """Кто я, что мне можно и куда меня пускать."""

    role_title = serializers.SerializerMethodField()
    domain = serializers.SerializerMethodField()
    domain_title = serializers.SerializerMethodField()
    student_id = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    identities = IdentitySerializer(many=True, read_only=True)
    can_see_whole_school = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "role",
            "role_title",
            "domain",
            "domain_title",
            "student_id",
            "group",
            "identities",
            "must_change_password",
            "sees_whole_school",
            "can_see_whole_school",
            "last_login",
            "sidebar_collapsed",
            "theme",
            "language",
        )
        read_only_fields = fields

    def get_role_title(self, obj: User) -> str:
        return ROLE_TITLES.get(obj.role, obj.role)

    def get_domain(self, obj: User) -> str | None:
        return obj.domain_code

    def get_domain_title(self, obj: User) -> str | None:
        code = obj.domain_code
        return DOMAINS[code].title if code else None

    def get_student_id(self, obj: User) -> int | None:
        student = getattr(obj, "student", None)
        return student.pk if student else None

    def get_group(self, obj: User) -> str | None:
        """Код учебной группы — есть только у ученика с карточкой."""
        student = getattr(obj, "student", None)
        return student.group.code if student and student.group else None


class PreferencesSerializer(serializers.Serializer):
    """Предпочтения интерфейса. Все поля необязательны — меняется что пришло."""

    sidebar_collapsed = serializers.BooleanField(required=False)
    theme = serializers.ChoiceField(choices=Theme.choices, required=False)
    language = serializers.ChoiceField(choices=Language.choices, required=False)


class LoginSerializer(serializers.Serializer):
    """Вход по почте и паролю."""

    email = serializers.EmailField()
    # пробелы в пароле значимы, обрезать их нельзя
    password = serializers.CharField(trim_whitespace=False, write_only=True)


class PasswordChangeSerializer(serializers.Serializer):
    """Смена пароля изнутри сессии."""

    current_password = serializers.CharField(trim_whitespace=False, write_only=True)
    new_password = serializers.CharField(trim_whitespace=False, write_only=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Установка пароля по одноразовой ссылке."""

    token = serializers.CharField(trim_whitespace=True)
    new_password = serializers.CharField(trim_whitespace=False, write_only=True)


class UserSerializer(serializers.ModelSerializer):
    """Строка списка пользователей для администратора."""

    role_title = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "full_name",
            "role",
            "role_title",
            "is_active",
            "sees_whole_school",
            "must_change_password",
            "has_password",
            "date_joined",
            "password_changed_at",
        )
        read_only_fields = fields

    def get_role_title(self, obj: User) -> str:
        return ROLE_TITLES.get(obj.role, obj.role)

    def get_has_password(self, obj: User) -> bool:
        return obj.has_usable_password()


class UserWriteSerializer(serializers.Serializer):
    """Заведение и правка учётной записи администратором.

    Пароля здесь нет намеренно: его человек устанавливает себе сам
    по одноразовой ссылке, чтобы администратор его не знал.
    """

    email = serializers.EmailField(required=False)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    sees_whole_school = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_full_name(self, value: str) -> str:
        """Имя с пометкой заглушки не заводим: см. `accounts.naming`."""
        try:
            return check_full_name(value)
        except NameRejected as error:
            raise serializers.ValidationError(str(error)) from error

    def validate(self, attrs):
        if self.partial is False and not attrs.get("email"):
            raise serializers.ValidationError({"email": "Почта обязательна"})
        return attrs


class InviteSerializer(serializers.Serializer):
    """Массовое приглашение: список почт одной строкой или списком."""

    emails = serializers.ListField(child=serializers.EmailField(), allow_empty=False, max_length=500)
    role = serializers.ChoiceField(choices=Role.choices, required=False)


class BulkUsersSerializer(serializers.Serializer):
    """Одно действие над несколькими отмеченными строками."""

    users = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=500)
    action = serializers.ChoiceField(choices=("invite", "temp_password", "deactivate"))


class CredentialsExportSerializer(serializers.Serializer):
    """Строки выгрузки: их отдаёт экран, сервер их не хранит."""

    rows = serializers.ListField(child=serializers.DictField(), allow_empty=False, max_length=1000)


class MagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class MagicLinkRedeemSerializer(serializers.Serializer):
    token = serializers.CharField(trim_whitespace=True)


class LinkIdentitySerializer(serializers.Serializer):
    """Привязка личной почты второй идентичностью."""

    email = serializers.EmailField()


class DetailSerializer(serializers.Serializer):
    """Короткий ответ-сообщение — чтобы OpenAPI-схема была полной."""

    detail = serializers.CharField()
