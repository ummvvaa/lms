"""Достижения-бейджи: прогресс, выдача, показ закрытых (фаза 46).

Два правила:

* **инвариант №12** — бейдж даётся за действия, а не за результат. Набор мер
  (`BadgeMetric`) закрыт и не содержит ни балла экзамена, ни GPA, ни статуса;
  порог у каждой записи свой, и новый бейдж заводится строкой без выката;
* **закрытые бейджи видны** — с замком и условием. Ученик должен видеть,
  что можно получить, иначе достижения превращаются в лотерею.
"""

from __future__ import annotations

from engagement.models import Badge, BadgeAward, BadgeMetric
from students.models import Student


def _value(student: Student, metric: str) -> int:
    """Текущее значение меры у ученика. Всё считается по действиям."""
    from engagement.models import XPEvent, XPKind
    from engagement.scoring import get_state

    if metric == BadgeMetric.TASKS_DONE:
        return XPEvent.objects.filter(student=student, kind=XPKind.TASK_DONE).count()
    if metric == BadgeMetric.EXERCISES_SOLVED:
        from prep.models import PracticeAnswer

        return PracticeAnswer.objects.filter(session__student=student, chosen__isnull=False).count()
    if metric == BadgeMetric.MOCKS_TAKEN:
        from prep.models import MockRun

        return MockRun.objects.filter(student=student, session__status="finished").count()
    if metric == BadgeMetric.PROFILE_SECTIONS:
        return XPEvent.objects.filter(student=student, kind=XPKind.PROFILE_SECTION).count()
    if metric == BadgeMetric.ESSAYS_STARTED:
        from roadmap.models import Essay

        return Essay.objects.filter(student=student).count()
    if metric == BadgeMetric.ONBOARDING_DONE:
        from engagement.models import OnboardingSession, OnboardingStatus

        return OnboardingSession.objects.filter(student=student, status=OnboardingStatus.COMPLETED).count()
    if metric == BadgeMetric.MATERIALS_APPROVED:
        return XPEvent.objects.filter(student=student, kind=XPKind.MATERIAL_APPROVED).count()
    if metric == BadgeMetric.RESOURCES_READ:
        from materials.models import ResourceRead

        return ResourceRead.objects.filter(student=student).count()
    if metric == BadgeMetric.STREAK_DAYS:
        state = get_state(student)
        return max(state.streak_days, state.best_streak)
    if metric == BadgeMetric.PLANS_CREATED:
        from roadmap.models import ApplicationPlan

        return ApplicationPlan.objects.filter(student=student).count()
    if metric == BadgeMetric.QUIZ_MATCHES:
        from prep.models import QuizPlayer

        return QuizPlayer.objects.filter(student=student, finished_at__isnull=False).count()
    if metric == BadgeMetric.DOCUMENTS_UPLOADED:
        from students.models import StudentDocument

        return StudentDocument.objects.filter(student=student).count()
    return 0


def refresh(student: Student) -> list[Badge]:
    """Пересчитать бейджи ученика и выдать заслуженные.

    Возвращает то, что выдано именно сейчас — по этому списку показывается
    уведомление «получен бейдж», а не по всему набору.
    """
    awarded: list[Badge] = []
    have = set(BadgeAward.objects.filter(student=student).values_list("badge_id", flat=True))
    for badge in Badge.objects.filter(is_active=True):
        if badge.pk in have:
            continue
        if _value(student, badge.metric) >= badge.threshold:
            BadgeAward.objects.get_or_create(student=student, badge=badge)
            awarded.append(badge)
    return awarded


def state_for(student: Student) -> dict:
    """Все бейджи с прогрессом: полученные и закрытые с условием.

    Прогресс показывается числом «92 из 100», а не только галочкой:
    «осталось восемь» двигает вперёд, а «не получено» — нет.
    """
    refresh(student)
    awarded = {row.badge_id: row.created_at for row in BadgeAward.objects.filter(student=student)}
    rows = []
    for badge in Badge.objects.filter(is_active=True):
        value = _value(student, badge.metric)
        done = badge.pk in awarded
        rows.append(
            {
                "id": badge.pk,
                "code": badge.code,
                "name": badge.name,
                "description": badge.description,
                "metric": badge.metric,
                "condition": f"{badge.get_metric_display()}: {badge.threshold}",
                "icon": badge.icon or "medal",
                "threshold": badge.threshold,
                "value": min(value, badge.threshold),
                "progress": f"{min(value, badge.threshold)} из {badge.threshold}",
                "percent": min(100, round(value / badge.threshold * 100)) if badge.threshold else 0,
                "earned": done,
                "earned_at": awarded.get(badge.pk),
            }
        )
    return {
        "earned": sum(1 for row in rows if row["earned"]),
        "total": len(rows),
        "badges": rows,
    }
