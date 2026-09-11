"""Инвариант №1 и №2: реестр доменов полон и без пересечений."""

from __future__ import annotations

import pytest
from django.apps import apps

from core import domains
from core.archivable import Archivable
from core.domains import DOMAINS, PROFILE_MODELS

#: Служебные поля, которые директор не редактирует и в реестре быть не должны.
#: Поля мягкого удаления берутся у самой базы, чтобы список не разъезжался.
NON_EDITABLE = {"id", "student", "created_at", "updated_at"} | {f.name for f in Archivable._meta.get_fields()}


def model_editable_fields(label: str) -> set[str]:
    """Редактируемые поля модели по её реальной схеме."""
    model = apps.get_model(label)
    names = set()
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False) or f.auto_created:
            continue
        if f.name in NON_EDITABLE:
            continue
        names.add(f.name)
    return names


def test_domains_cover_all_profile_fields():
    """Реестр покрывает все редактируемые поля пяти профильных моделей."""
    registry = domains.owned_fields_map()
    for label in PROFILE_MODELS:
        expected = model_editable_fields(label)
        actual = set(registry.get(label, {}))
        assert actual == expected, f"{label}: расхождение реестра и модели — {expected ^ actual}"


def test_no_overlap_between_domains():
    """Одно поле — ровно один домен."""
    seen: dict[tuple[str, str], str] = {}
    for domain, model, field in domains.iter_field_specs():
        key = (model.label, field.name)
        assert key not in seen, f"{key} принадлежит и {seen[key]}, и {domain.code}"
        seen[key] = domain.code


def test_every_registry_field_exists_on_model():
    """В реестре нет полей, которых нет в схеме."""
    for _domain, model, field in domains.iter_field_specs():
        real = {f.name for f in apps.get_model(model.label)._meta.get_fields()}
        assert field.name in real, f"{model.label}.{field.name} — поля нет в модели"


def test_five_profile_domains_have_five_different_roles():
    """Пять доменов с профилем ученика — пять разных ролей.

    Шестой домен «Документы» (фаза 60) принадлежит директору по поступлению
    вторым: у него нет профильной модели, и основной домен роли
    по-прежнему один — `domain_of_role` отвечает «Поступление».
    """
    profile_roles = [d.role for d in DOMAINS.values() if any(m.label in PROFILE_MODELS for m in d.models)]
    assert len(profile_roles) == len(set(profile_roles)) == 5
    assert domains.domain_of_role("director_admission").code == "admission"
    assert [d.code for d in domains.domains_of_role("director_admission")] == ["admission", "documents"]
    assert domains.can_write("director_admission", "students.StudentDocument", "note")
    assert not domains.can_write("director_exam", "students.StudentDocument", "note")
    assert not domains.can_write("curator", "students.StudentDocument", "note")


@pytest.mark.parametrize(
    "role,label,field_name,expected",
    [
        ("director_exam", "students.ExamProfile", "ielts_current", True),
        ("director_exam", "students.AdmissionProfile", "status", False),
        ("director_admission", "students.AdmissionProfile", "status", True),
        ("director_behavior", "students.BehaviorProfile", "attendance_percent", True),
        ("student", "students.ExamProfile", "ielts_current", False),
        # с фазы 68 администратор пишет во все домены — с пометкой в журнале
        ("admin", "students.ExamProfile", "ielts_current", True),
    ],
)
def test_can_write(role, label, field_name, expected):
    assert domains.can_write(role, label, field_name) is expected


def test_internal_labels_listed():
    """Ярлыки из инварианта №7 помечены в реестре."""
    labels = domains.internal_label_fields()
    assert {"status", "portfolio_status"} <= labels
    assert "portfolio_status" in domains.internal_label_fields("students.TalentProfile")
    assert "ielts_current" not in labels


def test_every_domain_names_exactly_one_profile_model():
    """Профиль домена помечен явно, а не «первой моделью в списке».

    Справочник, добавленный в домен, однажды уже увёл таблицу директора
    спорта на список видов спорта вместо профиля ученика (фаза 19).
    """
    from core.domains import DOMAINS, PROFILE_MODELS

    for domain in DOMAINS.values():
        profiles = [m.label for m in domain.models if m.label in PROFILE_MODELS]
        # домен документов (фаза 60) — единственный без профиля: документы
        # хранятся строками, а не полями ученика
        expected = 0 if domain.code == "documents" else 1
        assert len(profiles) == expected, f"{domain.code}: профилей {profiles}"
