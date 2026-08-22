"""Сериализаторы аутентификации и текущего пользователя."""

from __future__ import annotations

from rest_framework import serializers

from accounts.models import Identity, User
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
    identities = IdentitySerializer(many=True, read_only=True)

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
            "identities",
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


class EntraLoginSerializer(serializers.Serializer):
    """Тело запроса на вход через Microsoft."""

    id_token = serializers.CharField(trim_whitespace=True)


class LocalLoginSerializer(serializers.Serializer):
    """Локальный вход только для отладочного контура."""

    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, write_only=True)


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
