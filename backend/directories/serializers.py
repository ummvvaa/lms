"""Сериализаторы справочников."""

from __future__ import annotations

from rest_framework import serializers

from directories.models import ExamKind, OlympiadSubject, SportType
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
    def get_category_title(self, obj) -> str:
        return obj.get_area_display()

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
        return f"{low}–{obj.max_score}" if obj.max_score is not None else f"от {low}"

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
