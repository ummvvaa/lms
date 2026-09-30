"""Сериализаторы справочников."""

from __future__ import annotations

from django.utils.translation import gettext as _
from rest_framework import serializers

from directories.models import ExamKind, OlympiadSubject, SportType, SubjectArea
from directories.services import usage_total


class DirectorySerializer(serializers.ModelSerializer):
    """Общая часть: название, описание, видимость и число ссылок."""

    usage_total = serializers.SerializerMethodField()
    category_title = serializers.SerializerMethodField()

    def get_usage_total(self, obj) -> int:
        return usage_total(obj)

    def get_category_title(self, obj) -> str:
        raise NotImplementedError


class OlympiadSubjectSerializer(DirectorySerializer):
    #: пустое направление — не ошибка формы, а «Прочее»
    area = serializers.CharField(max_length=80, allow_blank=True, required=False)

    def get_category_title(self, obj) -> str:
        return obj.area

    def validate_area(self, value: str) -> str:
        """Своё направление — можно; второе такое же другим регистром — нет.

        «языки» и «Языки » приводятся к уже заведённому написанию: иначе
        список направлений расползается так же, как когда-то предметы.
        """
        text = " ".join(str(value or "").split())
        if not text:
            return SubjectArea.OTHER.label
        for known in OlympiadSubject.known_areas():
            if known.lower() == text.lower():
                return known
        return text[:1].upper() + text[1:]

    class Meta:
        model = OlympiadSubject
        fields = (
            "id",
            "name",
            "area",
            "category_title",
            "description",
            "is_active",
            "sort_order",
            "usage_total",
            "created_at",
        )
        read_only_fields = ("created_at",)


class SportTypeSerializer(DirectorySerializer):
    def get_category_title(self, obj) -> str:
        return obj.get_category_display()

    class Meta:
        model = SportType
        fields = (
            "id",
            "name",
            "category",
            "category_title",
            "description",
            "is_active",
            "sort_order",
            "usage_total",
            "created_at",
        )
        read_only_fields = ("created_at",)


class ReplaceSerializer(serializers.Serializer):
    """«Заменить»: перенести ссылки на другую запись и удалить эту."""

    target = serializers.IntegerField()


class ExamKindSerializer(DirectorySerializer):
    def get_category_title(self, obj) -> str:
        # у экзамена нет категории; в колонке показывается шкала
        if obj.min_score is None and obj.max_score is None:
            return ""
        low = obj.min_score if obj.min_score is not None else 0
        return f"{low}–{obj.max_score}" if obj.max_score is not None else _("от {low}").format(low=low)

    class Meta:
        model = ExamKind
        fields = (
            "id",
            "name",
            "min_score",
            "max_score",
            "category_title",
            "description",
            "is_active",
            "sort_order",
            "usage_total",
            "created_at",
        )
        read_only_fields = ("created_at",)
