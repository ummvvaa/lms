"""Материалы олимпиадников: разборы и решения, которыми делятся отобранные ученики.

Раздел закрыт олимпиадной группой: ученик вне её не видит его ни в меню,
ни по прямой ссылке, ни в API. Каждый материал проходит через Армана —
до одобрения его видят только автор и он.

Почему это не формальность. Официальные задания олимпиад, ещё не
опубликованные, и сканы чужих учебников школе хранить у себя не стоит:
претензии придут к школе, а не к ученику. Поэтому у каждого материала
есть заявленный тип источника и подтверждение права на публикацию —
решение принимает Арман, но перед глазами у него должен быть ответ.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.archivable import Archivable
from materials.storage import private_storage
from students.models import Student


class SourceKind(models.TextChoices):
    """Что это за материал — обязательный выбор при загрузке."""

    OWN_SOLUTION = "own_solution", "Моё решение"
    OWN_ANALYSIS = "own_analysis", "Мой разбор"
    THIRD_PARTY = "third_party", "Чужой материал"


class MaterialStatus(models.TextChoices):
    PENDING = "pending", "Ждёт проверки"
    APPROVED = "approved", "Одобрен"
    REJECTED = "rejected", "Отклонён"


class MaterialRequest(Archivable):
    """Запрос: «нужен разбор по такой-то теме».

    Виден всем в олимпиадной группе. Закрывается материалом, который
    прошёл проверку, — не самой загрузкой: иначе запрос закрывался бы
    тем, что Арман потом отклонит.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Открыт"
        CLOSED = "closed", "Закрыт"

    author = models.ForeignKey(
        Student, verbose_name="Кто просит", related_name="material_requests", on_delete=models.CASCADE
    )
    subject = models.ForeignKey(
        "directories.OlympiadSubject",
        verbose_name="Предмет",
        related_name="material_requests",
        on_delete=models.PROTECT,
    )
    topic = models.CharField("Тема", max_length=200)
    text = models.TextField("Что именно нужно", blank=True)
    status = models.CharField("Статус", max_length=8, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField("Закрыт", null=True, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Запрос материала"
        verbose_name_plural = "Запросы материалов"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "-created_at"))]

    def __str__(self) -> str:
        return f"{self.subject}: {self.topic}"


class StudyMaterial(Archivable):
    """Разбор или решение, загруженное учеником."""

    #: автор-ученик. Пусто — материал выложил сотрудник: у директора
    #: талантов карточки ученика нет, а раздел ведёт он, и свои разборы
    #: он кладёт туда же
    author = models.ForeignKey(
        Student, verbose_name="Автор", related_name="materials", on_delete=models.CASCADE, null=True, blank=True
    )
    staff_author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор-сотрудник",
        related_name="uploaded_materials",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    subject = models.ForeignKey(
        "directories.OlympiadSubject",
        verbose_name="Предмет",
        related_name="materials",
        on_delete=models.PROTECT,
    )
    topic = models.CharField("Тема", max_length=200)
    title = models.CharField("Название", max_length=250)
    description = models.TextField("Описание", blank=True)
    source_kind = models.CharField("Тип источника", max_length=16, choices=SourceKind.choices)
    #: «подтверждаю, что имею право это публиковать» — без галочки
    #: материал не заводится, и Арман видит ответ при проверке
    rights_confirmed = models.BooleanField("Право на публикацию подтверждено", default=False)
    status = models.CharField("Статус", max_length=10, choices=MaterialStatus.choices, default=MaterialStatus.PENDING)
    reject_reason = models.TextField("Причина отклонения", blank=True)
    request = models.ForeignKey(
        MaterialRequest,
        verbose_name="Закрывает запрос",
        related_name="materials",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    #: счётчик «было полезно». Публичного рейтинга авторов нет и не будет:
    #: ценность в материале, а не в соревновании между детьми
    helpful_count = models.PositiveIntegerField("Отметок «было полезно»", default=0)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто проверил",
        related_name="reviewed_materials",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField("Когда проверен", null=True, blank=True)
    created_at = models.DateTimeField("Загружен", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    @property
    def author_title(self) -> str:
        """Кто выложил — ученик или сотрудник."""
        if self.author_id:
            return self.author.full_name
        if self.staff_author_id:
            return self.staff_author.full_name or self.staff_author.email
        return "—"

    class Meta:
        verbose_name = "Материал"
        verbose_name_plural = "Материалы"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "-created_at")),
            models.Index(fields=("subject", "status")),
            models.Index(fields=("author", "-created_at")),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_public(self) -> bool:
        return self.status == MaterialStatus.APPROVED


def material_upload_to(instance: MaterialFile, filename: str) -> str:
    """Путь внутри закрытого хранилища. Имя файла задаём сами.

    Пришедшее от человека имя в путь не подставляем: в нём бывает и `..`,
    и что угодно ещё. Настоящее имя лежит рядом отдельным полем.
    """
    return f"materials/{instance.material_id}/{instance.pk or 'new'}-{instance.checksum[:16]}{instance.extension}"


class MaterialFile(models.Model):
    """Один файл материала.

    Лежит вне корня веб-сервера и отдаётся только через проверку прав:
    прямой ссылкой скачать нельзя (`materials.views.download`).
    """

    material = models.ForeignKey(StudyMaterial, verbose_name="Материал", related_name="files", on_delete=models.CASCADE)
    file = models.FileField("Файл", upload_to=material_upload_to, storage=private_storage, max_length=300)
    original_name = models.CharField("Имя файла", max_length=250)
    content_type = models.CharField("Тип содержимого", max_length=100)
    extension = models.CharField("Расширение", max_length=10)
    size = models.PositiveIntegerField("Размер, байт")
    checksum = models.CharField("Контрольная сумма", max_length=64)
    created_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Файл материала"
        verbose_name_plural = "Файлы материалов"
        ordering = ("id",)

    def __str__(self) -> str:
        return self.original_name


class MaterialHelpful(models.Model):
    """«Было полезно». Один голос от ученика на материал."""

    material = models.ForeignKey(
        StudyMaterial, verbose_name="Материал", related_name="helpful_marks", on_delete=models.CASCADE
    )
    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="helpful_marks", on_delete=models.CASCADE)
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Отметка «было полезно»"
        verbose_name_plural = "Отметки «было полезно»"
        constraints = [
            models.UniqueConstraint(fields=("material", "student"), name="uniq_helpful_per_student"),
        ]

    def __str__(self) -> str:
        return f"{self.student} → {self.material}"


class MaterialComment(Archivable):
    """Вопрос или замечание под материалом.

    Удаляется мягко: жалоба и уведомление на него ссылаются, и физическое
    удаление увело бы их в пустоту (инвариант №13).
    """

    material = models.ForeignKey(
        StudyMaterial, verbose_name="Материал", related_name="comments", on_delete=models.CASCADE
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Автор", related_name="material_comments", on_delete=models.CASCADE
    )
    text = models.TextField("Текст")
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Комментарий к материалу"
        verbose_name_plural = "Комментарии к материалам"
        ordering = ("created_at", "id")
        indexes = [models.Index(fields=("material", "created_at"))]

    def __str__(self) -> str:
        return f"{self.author} → {self.material}"


class MaterialReport(models.Model):
    """Жалоба на материал или комментарий. Уходит Арману."""

    class Status(models.TextChoices):
        OPEN = "open", "Ждёт разбора"
        RESOLVED = "resolved", "Разобрана"

    material = models.ForeignKey(
        StudyMaterial,
        verbose_name="Материал",
        related_name="reports",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    comment = models.ForeignKey(
        MaterialComment,
        verbose_name="Комментарий",
        related_name="reports",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто пожаловался",
        related_name="material_reports",
        on_delete=models.CASCADE,
    )
    reason = models.TextField("В чём дело")
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.OPEN)
    resolution = models.TextField("Что сделали", blank=True)
    created_at = models.DateTimeField("Когда", auto_now_add=True)
    resolved_at = models.DateTimeField("Разобрана", null=True, blank=True)

    class Meta:
        verbose_name = "Жалоба"
        verbose_name_plural = "Жалобы"
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(material__isnull=False) | models.Q(comment__isnull=False),
                name="report_points_somewhere",
            ),
        ]

    def __str__(self) -> str:
        return f"Жалоба #{self.pk}"


class MaterialCollection(models.Model):
    """Тематическая подборка: «Подготовка к республиканскому этапу по физике».

    Собирает её Арман. Порядок материалов внутри задаётся руками —
    подборка это маршрут, а не куча.
    """

    name = models.CharField("Название", max_length=200)
    description = models.TextField("Описание", blank=True)
    subject = models.ForeignKey(
        "directories.OlympiadSubject",
        verbose_name="Предмет",
        related_name="collections",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто собрал",
        related_name="material_collections",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)

    class Meta:
        verbose_name = "Подборка материалов"
        verbose_name_plural = "Подборки материалов"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class CollectionItem(models.Model):
    """Материал внутри подборки со своим порядком."""

    collection = models.ForeignKey(
        MaterialCollection, verbose_name="Подборка", related_name="items", on_delete=models.CASCADE
    )
    material = models.ForeignKey(
        StudyMaterial, verbose_name="Материал", related_name="in_collections", on_delete=models.CASCADE
    )
    position = models.PositiveSmallIntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Материал в подборке"
        verbose_name_plural = "Материалы в подборках"
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(fields=("collection", "material"), name="uniq_material_per_collection"),
        ]

    def __str__(self) -> str:
        return f"{self.collection} · {self.material}"


# --- Ресурсы: статьи и памятки школы (фаза 45) -----------------------------


class ResourceCategory(models.Model):
    """Категория материала: стипендии, заявки, вузы, подготовка, страны…

    Справочник, а не перечисление в коде: школа добавляет свои темы,
    и новая категория не должна означать выкат.
    """

    code = models.SlugField("Код", max_length=40, unique=True)
    name = models.CharField("Название", max_length=120)
    description = models.CharField("Описание", max_length=250, blank=True)
    #: смысловой цвет полосы карточки — имя токена, а не число (дизайн-система)
    accent = models.CharField(
        "Цвет полосы",
        max_length=16,
        blank=True,
        help_text="brand, teal, indigo, ok, warn — токен из дизайн-системы",
    )
    order = models.PositiveSmallIntegerField("Порядок", default=100)
    is_active = models.BooleanField("Показывать", default=True)

    class Meta:
        verbose_name = "Категория материалов"
        verbose_name_plural = "Категории материалов"
        ordering = ("order", "name")

    def __str__(self) -> str:
        return self.name


class Resource(models.Model):
    """Статья или памятка школы.

    Это не материалы олимпиадников: у тех закрытый раздел и файлы, а здесь
    открытый текст, который школа и так пишет — и который сейчас лежит
    в чатах и теряется. Владельца-домена у ресурса нет: ведут его пять
    директоров, каждый по своей теме, и в строке видно, кто написал.
    """

    title = models.CharField("Заголовок", max_length=200)
    category = models.ForeignKey(
        ResourceCategory, verbose_name="Категория", related_name="resources", on_delete=models.PROTECT
    )
    summary = models.CharField("Короткое описание", max_length=300, blank=True)
    body = models.TextField("Текст", blank=True)
    reading_minutes = models.PositiveSmallIntegerField("Время чтения, минут", default=5)
    #: метки строкой через запятую — как требуемые предметы у требований вуза
    tags = models.CharField("Метки", max_length=250, blank=True, help_text="Через запятую")
    is_featured = models.BooleanField("Рекомендуем", default=False)
    is_published = models.BooleanField("Показывать ученикам", default=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        related_name="resources",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    published_on = models.DateField("Дата публикации", null=True, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Материал раздела «Ресурсы»"
        verbose_name_plural = "Материалы раздела «Ресурсы»"
        ordering = ("-is_featured", "-published_on", "-created_at")
        indexes = [models.Index(fields=("category", "is_published"))]

    def __str__(self) -> str:
        return self.title

    @property
    def tags_list(self) -> list[str]:
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]


class ResourceRead(models.Model):
    """Отметка «прочитано». Ставит и снимает сам ученик.

    XP за неё не начисляется: нажатие — не действие, за которое стоит
    награждать, иначе выгоднее отметить всё подряд (инвариант №12).
    """

    resource = models.ForeignKey(Resource, verbose_name="Материал", related_name="reads", on_delete=models.CASCADE)
    student = models.ForeignKey(Student, verbose_name="Ученик", related_name="resource_reads", on_delete=models.CASCADE)
    created_at = models.DateTimeField("Когда", auto_now_add=True)

    class Meta:
        verbose_name = "Прочитанный материал"
        verbose_name_plural = "Прочитанные материалы"
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("resource", "student"), name="uniq_resource_read")]

    def __str__(self) -> str:
        return f"{self.student} прочитал «{self.resource}»"
