"""Материалы олимпиадников: доступ, модерация, файлы, полезность, запросы."""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from accounts.models import Role
from core.models import Notification
from directories.models import OlympiadSubject
from engagement.models import XPEvent, XPKind
from materials.files import FileRejected, inspect
from materials.models import (
    MaterialCollection,
    MaterialComment,
    MaterialReport,
    MaterialRequest,
    MaterialStatus,
    SourceKind,
    StudyMaterial,
)
from students.models import Activity, Student

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
NOT_A_PDF = b"MZ\x90\x00" + b"\x00" * 64


def pdf(name: str = "razbor.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, PDF, content_type="application/pdf")


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def arman(make_user):
    return make_user(Role.DIRECTOR_TALENT, email="arman.materials@example.kz")


@pytest.fixture
def subject(db) -> OlympiadSubject:
    return OlympiadSubject.objects.create(name="Физика", area="natural")


def make_student(email: str, *, in_group: bool, make_user, group) -> Student:
    user = make_user(Role.STUDENT, email=email)
    student = Student.objects.create(
        last_name="Ученик",
        first_name=email.split("@")[0],
        email=email,
        grade=11,
        group=group,
        graduation_year=2027,
        user=user,
        in_olympiad_group=in_group,
    )
    return student


@pytest.fixture
def olympian(make_user, group) -> Student:
    return make_student("olympian@example.kz", in_group=True, make_user=make_user, group=group)


@pytest.fixture
def outsider(make_user, group) -> Student:
    return make_student("outsider@example.kz", in_group=False, make_user=make_user, group=group)


@pytest.fixture
def material(olympian, subject) -> StudyMaterial:
    return StudyMaterial.objects.create(
        author=olympian,
        subject=subject,
        topic="Механика",
        title="Разбор задач по механике",
        source_kind=SourceKind.OWN_ANALYSIS,
        rights_confirmed=True,
    )


# --- Доступ ---------------------------------------------------------------

SECTION_PATHS = (
    "/api/materials/",
    "/api/material-requests/",
    "/api/material-collections/",
    "/api/material-comments/",
)


@pytest.mark.django_db
@pytest.mark.parametrize("path", SECTION_PATHS)
def test_student_outside_the_group_gets_404_everywhere(api, outsider, path):
    """Раздела для него не существует — ни 403, ни пустого списка."""
    api.force_authenticate(outsider.user)
    assert api.get(path).status_code == 404


@pytest.mark.django_db
def test_student_outside_the_group_is_not_told_the_section_exists(api, outsider):
    """Даже состояние раздела не выдаёт, что кого-то туда пускают."""
    api.force_authenticate(outsider.user)
    state = api.get("/api/materials-state/").json()
    assert state["has_access"] is False
    assert state["is_curator"] is False


@pytest.mark.django_db
def test_group_member_gets_the_section(api, olympian):
    api.force_authenticate(olympian.user)
    assert api.get("/api/materials/").status_code == 200
    assert api.get("/api/materials-state/").json()["has_access"] is True


@pytest.mark.django_db
def test_only_the_talent_director_picks_the_group(api, arman, make_user, outsider):
    """Признак ставит владелец домена, чужой директор — нет (инвариант №1)."""
    exam = make_user(Role.DIRECTOR_EXAM, email="kymbat.group@example.kz")
    api.force_authenticate(exam)
    assert (
        api.post("/api/olympiad-group/pick/", {"student": outsider.pk, "member": True}, format="json").status_code
        == 403
    )

    api.force_authenticate(arman)
    answer = api.post("/api/olympiad-group/pick/", {"student": outsider.pk, "member": True}, format="json")
    assert answer.status_code == 200
    assert "раздел материалов ему открыт" in answer.json()["detail"]

    outsider.refresh_from_db()
    assert outsider.in_olympiad_group is True

    # правка признака попала в журнал (инвариант №9)
    from core.models import AuditLog

    assert AuditLog.objects.filter(field_name="in_olympiad_group", student_id=outsider.pk).exists()


@pytest.mark.django_db
def test_removing_from_the_group_closes_the_section(api, arman, olympian):
    api.force_authenticate(arman)
    api.post("/api/olympiad-group/pick/", {"student": olympian.pk, "member": False}, format="json")

    from accounts.models import User

    # берём учётную запись заново: связь `user.student` кешируется на объекте,
    # а в реальном запросе пользователь всегда читается из базы
    api.force_authenticate(User.objects.get(pk=olympian.user_id))
    assert api.get("/api/materials/").status_code == 404


# --- Модерация -------------------------------------------------------------


@pytest.mark.django_db
def test_uploaded_material_is_invisible_to_everyone_but_author_and_curator(api, material, make_user, group, arman):
    """До одобрения материал видят только автор и Арман."""
    other = make_student("other@example.kz", in_group=True, make_user=make_user, group=group)

    api.force_authenticate(other.user)
    assert api.get("/api/materials/").json()["results"] == []
    assert api.get(f"/api/materials/{material.pk}/").status_code == 404

    api.force_authenticate(material.author.user)
    assert [row["id"] for row in api.get("/api/materials/").json()["results"]] == [material.pk]

    api.force_authenticate(arman)
    assert [row["id"] for row in api.get("/api/materials/").json()["results"]] == [material.pk]


@pytest.mark.django_db
def test_approval_awards_xp_and_creates_an_activity(api, arman, material):
    """После одобрения — XP автору и запись в активностях, а не при загрузке."""
    assert not XPEvent.objects.filter(student=material.author).exists()

    api.force_authenticate(arman)
    answer = api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json").json()

    assert answer["status"] == MaterialStatus.APPROVED
    assert answer["xp"] > 0

    event = XPEvent.objects.get(student=material.author, kind=XPKind.MATERIAL_APPROVED)
    assert event.object_id == str(material.pk)

    activity = Activity.objects.get(student=material.author, title=f"Материал: {material.title}")
    assert activity.subject_id == material.subject_id
    assert activity.is_confirmed is True


@pytest.mark.django_db
def test_xp_is_given_once_even_after_a_second_approval(api, arman, material):
    api.force_authenticate(arman)
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "reject", "reason": "передумал"}, format="json")
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")

    assert XPEvent.objects.filter(student=material.author, kind=XPKind.MATERIAL_APPROVED).count() == 1
    assert Activity.objects.filter(student=material.author, title=f"Материал: {material.title}").count() == 1


@pytest.mark.django_db
def test_rejected_material_stays_out_of_the_library_but_author_sees_the_reason(api, arman, material, make_user, group):
    api.force_authenticate(arman)
    api.post(
        f"/api/materials/{material.pk}/review/",
        {"decision": "reject", "reason": "Это скан чужого учебника"},
        format="json",
    )

    other = make_student("reader@example.kz", in_group=True, make_user=make_user, group=group)
    api.force_authenticate(other.user)
    assert api.get("/api/materials/?status=approved").json()["results"] == []
    assert api.get("/api/materials/").json()["results"] == []

    api.force_authenticate(material.author.user)
    row = api.get(f"/api/materials/{material.pk}/").json()
    assert row["status_title"] == "Отклонён"
    assert row["reject_reason"] == "Это скан чужого учебника"


@pytest.mark.django_db
def test_rejection_without_a_reason_is_refused(api, arman, material):
    api.force_authenticate(arman)
    answer = api.post(f"/api/materials/{material.pk}/review/", {"decision": "reject"}, format="json")
    assert answer.status_code == 400
    assert "причины" in str(answer.json())


@pytest.mark.django_db
def test_only_the_curator_reviews(api, olympian, material):
    api.force_authenticate(olympian.user)
    assert api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json").status_code == 403


# --- Загрузка и файлы ------------------------------------------------------


@pytest.mark.django_db
def test_upload_requires_the_rights_checkbox(api, olympian, subject):
    """Без подтверждения права на публикацию материал не заводится."""
    api.force_authenticate(olympian.user)
    answer = api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Оптика",
            "title": "Задачи по оптике",
            "source_kind": SourceKind.THIRD_PARTY,
            "rights_confirmed": False,
        },
        format="json",
    )
    assert answer.status_code == 400
    assert "права на публикацию" in str(answer.json())
    assert StudyMaterial.objects.count() == 0


@pytest.mark.django_db
def test_upload_stores_the_declared_source_kind_for_the_curator(api, olympian, subject, arman):
    api.force_authenticate(olympian.user)
    created = api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Оптика",
            "title": "Задачи по оптике",
            "source_kind": SourceKind.THIRD_PARTY,
            "rights_confirmed": True,
            "files": pdf(),
        },
        format="multipart",
    )
    assert created.status_code == 201, created.data

    api.force_authenticate(arman)
    queue = api.get("/api/materials/queue/").json()
    assert queue["pending"][0]["source_kind_title"] == "Чужой материал"
    assert queue["pending"][0]["rights_confirmed"] is True
    assert "1 материал ждёт проверки" in queue["summary"]


@pytest.mark.django_db
def test_file_type_is_checked_by_content_not_by_extension():
    """`.pdf` дописывается к чему угодно — смотрим первые байты."""
    fake = SimpleUploadedFile("razbor.pdf", NOT_A_PDF, content_type="application/pdf")
    with pytest.raises(FileRejected) as error:
        inspect(fake)
    assert "не похож на PDF, JPG или PNG" in str(error.value)

    good = inspect(SimpleUploadedFile("shot.png", PNG, content_type="image/png"))
    assert good.content_type == "image/png"
    assert good.extension == ".png"


@pytest.mark.django_db
def test_oversized_file_is_refused_in_words(settings):
    settings.MATERIAL_MAX_FILE_MB = 1
    big = SimpleUploadedFile("big.pdf", b"%PDF-" + b"0" * (2 * 1024 * 1024), content_type="application/pdf")
    with pytest.raises(FileRejected) as error:
        inspect(big)
    assert "а можно до 1 МБ" in str(error.value)


@pytest.mark.django_db
def test_too_many_files_are_refused(api, olympian, subject, settings):
    settings.MATERIAL_MAX_FILES = 2
    api.force_authenticate(olympian.user)
    answer = api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Оптика",
            "title": "Задачи",
            "source_kind": SourceKind.OWN_SOLUTION,
            "rights_confirmed": True,
            "files": [pdf("a.pdf"), pdf("b.pdf"), pdf("c.pdf")],
        },
        format="multipart",
    )
    assert answer.status_code == 400
    assert "вместе больше 2" in str(answer.json())


@pytest.mark.django_db
def test_file_is_served_only_through_the_check(api, olympian, subject, arman, make_user, group):
    """Прямой ссылки нет: файл отдаёт вьюха, и только тем, кто вправе."""
    api.force_authenticate(olympian.user)
    created = api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Оптика",
            "title": "Задачи",
            "source_kind": SourceKind.OWN_SOLUTION,
            "rights_confirmed": True,
            "files": pdf(),
        },
        format="multipart",
    ).json()
    file_id = created["files"][0]["id"]
    assert created["files"][0]["url"] == f"/api/materials/files/{file_id}/"

    # автор — можно
    assert api.get(f"/api/materials/files/{file_id}/").status_code == 200

    # одногруппник до одобрения — нет
    other = make_student("peer@example.kz", in_group=True, make_user=make_user, group=group)
    api.force_authenticate(other.user)
    assert api.get(f"/api/materials/files/{file_id}/").status_code == 404

    # после одобрения — можно
    api.force_authenticate(arman)
    api.post(f"/api/materials/{created['id']}/review/", {"decision": "approve"}, format="json")
    api.force_authenticate(other.user)
    answer = api.get(f"/api/materials/files/{file_id}/")
    assert answer.status_code == 200
    assert answer["Cache-Control"] == "private, no-store"

    # а вне группы — нет никогда
    outsider = make_student("nogroup@example.kz", in_group=False, make_user=make_user, group=group)
    api.force_authenticate(outsider.user)
    assert api.get(f"/api/materials/files/{file_id}/").status_code == 404


@pytest.mark.django_db
def test_files_live_outside_the_served_directory(api, olympian, subject, settings):
    """Файл не должен оказаться в /media/, который nginx раздаёт сам."""
    api.force_authenticate(olympian.user)
    created = api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Оптика",
            "title": "Задачи",
            "source_kind": SourceKind.OWN_SOLUTION,
            "rights_confirmed": True,
            "files": pdf(),
        },
        format="multipart",
    ).json()

    from materials.models import MaterialFile

    row = MaterialFile.objects.get(pk=created["files"][0]["id"])
    assert str(settings.PRIVATE_MEDIA_ROOT) in row.file.path
    assert str(settings.MEDIA_ROOT) not in row.file.path
    with pytest.raises(ValueError):
        _ = row.file.url


# --- Полезность, комментарии, жалобы ---------------------------------------


@pytest.mark.django_db
def test_helpful_is_one_vote_per_student_and_there_is_no_author_ranking(api, arman, material, make_user, group):
    api.force_authenticate(arman)
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")

    reader = make_student("voter@example.kz", in_group=True, make_user=make_user, group=group)
    api.force_authenticate(reader.user)

    first = api.post(f"/api/materials/{material.pk}/helpful/").json()
    assert first == {"marked": True, "helpful_count": 1, "detail": "Спасибо, отметили"}
    second = api.post(f"/api/materials/{material.pk}/helpful/").json()
    assert second["marked"] is False and second["helpful_count"] == 0

    api.post(f"/api/materials/{material.pk}/helpful/")
    api.post(f"/api/materials/{material.pk}/helpful/")
    material.refresh_from_db()
    assert material.helpful_count in (0, 1)

    # публичного рейтинга авторов в API нет
    from django.urls import get_resolver

    routes = " ".join(str(pattern.pattern) for pattern in get_resolver().url_patterns)
    assert "leaderboard" not in routes and "top-authors" not in routes


@pytest.mark.django_db
def test_comment_notifies_the_author_and_the_curator(api, arman, material, make_user, group):
    api.force_authenticate(arman)
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")
    Notification.objects.all().delete()

    reader = make_student("asker@example.kz", in_group=True, make_user=make_user, group=group)
    api.force_authenticate(reader.user)
    api.post(
        "/api/material-comments/",
        {"material": material.pk, "text": "А откуда взялось третье уравнение?"},
        format="json",
    )

    assert Notification.objects.filter(recipient=material.author.user).exists()
    assert Notification.objects.filter(recipient=arman).exists()


@pytest.mark.django_db
def test_curator_removes_a_foreign_comment_but_a_student_cannot(api, arman, material, make_user, group):
    api.force_authenticate(arman)
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")

    reader = make_student("commenter@example.kz", in_group=True, make_user=make_user, group=group)
    comment = MaterialComment.objects.create(material=material, author=reader.user, text="вопрос")

    stranger = make_student("stranger@example.kz", in_group=True, make_user=make_user, group=group)
    api.force_authenticate(stranger.user)
    assert api.delete(f"/api/material-comments/{comment.pk}/").status_code == 403

    api.force_authenticate(arman)
    assert api.delete(f"/api/material-comments/{comment.pk}/").status_code == 200
    assert not MaterialComment.objects.filter(pk=comment.pk).exists()
    assert MaterialComment.all_objects.filter(pk=comment.pk).exists()


@pytest.mark.django_db
def test_report_goes_to_the_curator(api, arman, material, olympian):
    api.force_authenticate(olympian.user)
    created = api.post(
        "/api/material-reports/",
        {"material": material.pk, "reason": "Это опубликованные задания этого года"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert Notification.objects.filter(recipient=arman, kind=Notification.Kind.MATERIAL_REPORT).exists()

    api.force_authenticate(arman)
    queue = api.get("/api/materials/queue/").json()
    assert len(queue["reports"]) == 1
    assert "1 жалоба не разобрано" in queue["summary"]

    resolved = api.post(
        f"/api/material-reports/{created.json()['id']}/resolve/", {"resolution": "Убрал материал"}, format="json"
    )
    assert resolved.status_code == 200
    assert MaterialReport.objects.get(pk=created.json()["id"]).status == MaterialReport.Status.RESOLVED


# --- Подборки и запросы ----------------------------------------------------


@pytest.mark.django_db
def test_collection_takes_only_approved_materials(api, arman, material):
    api.force_authenticate(arman)
    collection = api.post(
        "/api/material-collections/",
        {"name": "Подготовка к республиканскому этапу по физике", "description": "Порядок разборов"},
        format="json",
    ).json()

    refused = api.post(f"/api/material-collections/{collection['id']}/add/", {"material": material.pk}, format="json")
    assert refused.status_code == 400
    assert "только одобренные" in refused.json()["detail"]

    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")
    added = api.post(
        f"/api/material-collections/{collection['id']}/add/",
        {"material": material.pk, "position": 1},
        format="json",
    )
    assert added.status_code == 200

    rows = api.get(f"/api/material-collections/{collection['id']}/").json()["items"]
    assert [row["title"] for row in rows] == [material.title]


@pytest.mark.django_db
def test_students_cannot_build_collections(api, olympian):
    api.force_authenticate(olympian.user)
    assert api.post("/api/material-collections/", {"name": "Своя подборка"}, format="json").status_code == 403


@pytest.mark.django_db
def test_request_is_closed_by_an_approved_material_not_by_the_upload(api, arman, olympian, subject, make_user, group):
    api.force_authenticate(olympian.user)
    request_row = api.post(
        "/api/material-requests/",
        {"subject": subject.pk, "topic": "Термодинамика", "text": "Нужен разбор второго начала"},
        format="json",
    ).json()

    helper = make_student("helper@example.kz", in_group=True, make_user=make_user, group=group)
    api.force_authenticate(helper.user)
    material = api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Термодинамика",
            "title": "Второе начало на пальцах",
            "source_kind": SourceKind.OWN_ANALYSIS,
            "rights_confirmed": True,
            "request": request_row["id"],
        },
        format="json",
    ).json()

    assert MaterialRequest.objects.get(pk=request_row["id"]).status == MaterialRequest.Status.OPEN

    api.force_authenticate(arman)
    answer = api.post(f"/api/materials/{material['id']}/review/", {"decision": "approve"}, format="json").json()
    assert answer["closed_request"] == request_row["id"]
    assert MaterialRequest.objects.get(pk=request_row["id"]).status == MaterialRequest.Status.CLOSED
    assert Notification.objects.filter(recipient=olympian.user, kind=Notification.Kind.MATERIAL_REQUEST).exists()


@pytest.mark.django_db
def test_requests_are_visible_to_the_whole_group(api, olympian, subject, make_user, group):
    MaterialRequest.objects.create(author=olympian, subject=subject, topic="Кинематика")
    peer = make_student("peer2@example.kz", in_group=True, make_user=make_user, group=group)
    api.force_authenticate(peer.user)
    assert [row["topic"] for row in api.get("/api/material-requests/").json()["results"]] == ["Кинематика"]


# --- Уведомления -----------------------------------------------------------


@pytest.mark.django_db
def test_notifications_are_personal_and_readable(api, arman, material, olympian):
    api.force_authenticate(arman)
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")

    api.force_authenticate(olympian.user)
    rows = api.get("/api/notifications/").json()
    assert rows["unread"] >= 1
    assert "одобрен" in rows["rows"][0]["text"]
    assert "_" not in rows["rows"][0]["text"]

    api.post("/api/notifications/read/", {}, format="json")
    assert api.get("/api/notifications/").json()["unread"] == 0


@pytest.mark.django_db
def test_the_upload_notifies_the_curator(api, olympian, subject, arman):
    api.force_authenticate(olympian.user)
    api.post(
        "/api/materials/",
        {
            "subject": subject.pk,
            "topic": "Оптика",
            "title": "Задачи",
            "source_kind": SourceKind.OWN_SOLUTION,
            "rights_confirmed": True,
        },
        format="json",
    )
    assert Notification.objects.filter(recipient=arman, kind=Notification.Kind.MATERIAL_PENDING).exists()


def test_pdf_signature_is_not_confused_with_a_text_file():
    """Файл, начинающийся не с сигнатуры, не проходит."""
    with pytest.raises(FileRejected):
        inspect(SimpleUploadedFile("notes.pdf", io.BytesIO(b"just text").read(), content_type="text/plain"))


@pytest.mark.django_db
def test_mine_shows_own_materials_including_rejected(api, arman, material, make_user, group):
    """«Мои материалы» — свои целиком, чужие туда не попадают."""
    other = make_student("mine.other@example.kz", in_group=True, make_user=make_user, group=group)
    StudyMaterial.objects.create(
        author=other,
        subject=material.subject,
        topic="Оптика",
        title="Чужой разбор",
        source_kind=SourceKind.OWN_ANALYSIS,
        rights_confirmed=True,
        status=MaterialStatus.APPROVED,
    )
    api.force_authenticate(arman)
    api.post(
        f"/api/materials/{material.pk}/review/",
        {"decision": "reject", "reason": "нужны источники"},
        format="json",
    )

    api.force_authenticate(material.author.user)
    rows = api.get("/api/materials/?mine=true").json()["results"]
    assert [row["title"] for row in rows] == [material.title]
    assert rows[0]["reject_reason"] == "нужны источники"


@pytest.mark.django_db
def test_collection_is_visible_to_the_group(api, arman, material, olympian):
    """Подборку собирает Арман, читает вся группа."""
    api.force_authenticate(arman)
    api.post(f"/api/materials/{material.pk}/review/", {"decision": "approve"}, format="json")
    collection = api.post("/api/material-collections/", {"name": "Физика: республика"}, format="json").json()
    api.post(f"/api/material-collections/{collection['id']}/add/", {"material": material.pk}, format="json")

    api.force_authenticate(olympian.user)
    rows = api.get("/api/material-collections/").json()["results"]
    assert rows[0]["name"] == "Физика: республика"
    assert rows[0]["items"][0]["title"] == material.title
    assert MaterialCollection.objects.count() == 1


# --- Кому раздел вообще виден (фаза 26) -----------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [Role.DIRECTOR_BEHAVIOR, Role.DIRECTOR_ADMISSION, Role.DIRECTOR_EXAM, Role.DIRECTOR_SPORT, Role.ADMIN],
)
@pytest.mark.parametrize("path", SECTION_PATHS)
def test_other_staff_have_no_materials_section(api, make_user, role, path):
    """Раздел ведёт директор талантов — у остальных его нет и по адресу.

    Убрать пункт из меню мало: экран открывается ссылкой, и отказ должен
    приходить с сервера.
    """
    user = make_user(role, email=f"{role}.materials@example.kz")
    api.force_authenticate(user)
    assert api.get(path).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "role",
    [Role.DIRECTOR_BEHAVIOR, Role.DIRECTOR_ADMISSION, Role.DIRECTOR_EXAM, Role.DIRECTOR_SPORT, Role.ADMIN],
)
def test_other_staff_are_not_offered_the_menu_item(api, make_user, role):
    """Меню строится по этому же ответу — пункта у них не появится."""
    user = make_user(role, email=f"{role}.state@example.kz")
    api.force_authenticate(user)
    state = api.get("/api/materials-state/").json()
    assert state["has_access"] is False
    assert state["is_curator"] is False


@pytest.mark.django_db
def test_talent_director_keeps_the_section(api, arman):
    api.force_authenticate(arman)
    assert api.get("/api/materials/").status_code == 200
    state = api.get("/api/materials-state/").json()
    assert state["has_access"] is True
    assert state["is_curator"] is True
