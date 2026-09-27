"""Сериализаторы центра подготовки."""

from __future__ import annotations

from rest_framework import serializers

from prep.models import (
    OPEN_SECTIONS,
    OPEN_TYPES,
    Difficulty,
    MockExam,
    MockSection,
    PassageKind,
    Question,
    QuestionOption,
    QuestionPassage,
    QuestionType,
    Section,
    TheoryLesson,
)
from students.models import ExamType

#: Аудио задания на аудирование: что принимает форма. Массовая загрузка
#: банка кладёт файлы своим путём и сюда не заходит
AUDIO_EXTENSIONS = (".mp3", ".m4a")
AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4"}
AUDIO_MAX_MB = 20


class QuestionOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionOption
        fields = ("id", "letter", "text", "is_correct")


class PassageSerializer(serializers.ModelSerializer):
    """Источник для группы вопросов: текст чтения или аудио аудирования.

    Форма банка заводит его руками — то же, что массовая загрузка делает
    из колонок `passage_*`. Аудио уходит файлом (multipart), отдаётся
    своим маршрутом после входа, как документы.
    """

    audio = serializers.FileField(write_only=True, required=False, allow_null=True)
    has_audio = serializers.SerializerMethodField()
    audio_url = serializers.SerializerMethodField()
    questions_count = serializers.SerializerMethodField()

    class Meta:
        model = QuestionPassage
        fields = (
            "id",
            "exam_type",
            "section",
            "kind",
            "title",
            "body",
            "audio",
            "has_audio",
            "audio_url",
            "audio_start",
            "audio_end",
            "source",
            "is_active",
            "questions_count",
        )

    def get_has_audio(self, obj) -> bool:
        return bool(obj.audio)

    def get_audio_url(self, obj) -> str:
        return f"/api/prep/passages/{obj.pk}/audio/" if obj.audio else ""

    def get_questions_count(self, obj) -> int:
        return obj.questions.filter(is_active=True).count()

    def validate_audio(self, upload):
        if upload is None:
            return upload
        name = (upload.name or "").lower()
        if not name.endswith(AUDIO_EXTENSIONS):
            raise serializers.ValidationError("Аудио — файлом mp3 или m4a")
        if upload.size > AUDIO_MAX_MB * 1024 * 1024:
            raise serializers.ValidationError(f"Аудио тяжелее {AUDIO_MAX_MB} МБ — сожмите или разрежьте запись")
        return upload

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", ""))
        has_audio = bool(attrs.get("audio")) or bool(getattr(self.instance, "audio", None))
        body = attrs.get("body", getattr(self.instance, "body", ""))
        if kind == PassageKind.LISTENING and not has_audio:
            raise serializers.ValidationError(
                {"audio": "Аудирование без аудио не сохраняется: приложите файл mp3 или m4a"}
            )
        if kind == PassageKind.READING and not str(body or "").strip():
            raise serializers.ValidationError({"body": "У текста для чтения нужен сам текст"})
        return attrs

    def _store_audio(self, passage, upload):
        if upload is None:
            return
        extension = next(ext for ext in AUDIO_EXTENSIONS if upload.name.lower().endswith(ext))
        passage.audio.save(upload.name, upload, save=False)
        passage.audio_content_type = AUDIO_TYPES[extension]
        passage.save(update_fields=["audio", "audio_content_type"])

    def create(self, validated_data):
        upload = validated_data.pop("audio", None)
        passage = QuestionPassage.objects.create(**validated_data)
        self._store_audio(passage, upload)
        return passage

    def update(self, instance, validated_data):
        upload = validated_data.pop("audio", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save()
        self._store_audio(instance, upload)
        return instance


class QuestionSerializer(serializers.ModelSerializer):
    """Задание с вариантами. Верный ответ виден только сотрудникам.

    Состав задания зависит от секции — то же умеет файл массовой загрузки:

    * Listening — источник с аудио обязателен, плюс варианты и верный ответ;
    * Reading — вопрос к пассажу (текст один, вопросов несколько), с вариантами;
    * Writing, Speaking — открытый ответ: вариантов нет, есть критерии и предел;
    * остальное (SAT и прочее) — варианты; пассаж по желанию.
    """

    options = QuestionOptionSerializer(many=True, required=False)
    passage_title = serializers.CharField(source="passage.title", read_only=True, default="")

    class Meta:
        model = Question
        fields = (
            "id",
            "exam_type",
            "section",
            "topic",
            "subtopic",
            "difficulty",
            "question_type",
            "text",
            "explanation",
            "criteria",
            "sample_answer",
            "word_limit",
            "minute_limit",
            "expected_seconds",
            "source",
            "source_year",
            "passage",
            "passage_title",
            "is_active",
            "options",
        )

    def validate(self, attrs):
        def value(name, default=None):
            return attrs.get(name, getattr(self.instance, name, default))

        section = value("section", "")
        passage = value("passage")
        options = attrs.get("options")
        if options is None and self.instance is not None:
            options = list(self.instance.options.values("letter", "text", "is_correct"))
        options = options or []

        if section in OPEN_SECTIONS:
            # открытое задание: тип следует из секции, вариантов не бывает
            attrs["question_type"] = QuestionType.WRITING if section == Section.WRITING else QuestionType.SPEAKING
            if options:
                raise serializers.ValidationError({"options": "У Writing и Speaking вариантов ответа не бывает"})
            attrs["options"] = []
            return attrs

        if value("question_type") in OPEN_TYPES:
            attrs["question_type"] = QuestionType.SINGLE
        if section == Section.LISTENING and (passage is None or not passage.audio):
            raise serializers.ValidationError({"passage": "Задание на аудирование не сохраняется без аудио"})
        if section == Section.READING and passage is None:
            raise serializers.ValidationError({"passage": "Вопрос по чтению заводится к пассажу — сначала текст"})
        if passage is not None and (passage.exam_type != value("exam_type") or passage.section != section):
            raise serializers.ValidationError({"passage": "Источник заведён для другого экзамена или секции"})
        kind = value("question_type", QuestionType.SINGLE)
        if kind == QuestionType.SHORT:
            return attrs  # короткий ответ приходит из файла: вариантов у него нет
        filled = [option for option in options if str(option.get("text") or "").strip()]
        if len(filled) < 2:
            raise serializers.ValidationError({"options": "Нужно хотя бы два варианта ответа"})
        correct = sum(1 for option in filled if option.get("is_correct"))
        if kind == QuestionType.MULTIPLE and correct < 1:
            raise serializers.ValidationError({"options": "Отметьте верные варианты"})
        if kind != QuestionType.MULTIPLE and correct != 1:
            raise serializers.ValidationError({"options": "Верный вариант — ровно один"})
        return attrs

    def create(self, validated_data):
        options = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)
        for option in options:
            QuestionOption.objects.create(question=question, **option)
        return question

    def update(self, instance, validated_data):
        options = validated_data.pop("options", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if options is not None:
            instance.options.all().delete()
            for option in options:
                QuestionOption.objects.create(question=instance, **option)
        return instance


class MockSectionSerializer(serializers.ModelSerializer):
    section_title = serializers.CharField(source="get_section_display", read_only=True)

    class Meta:
        model = MockSection
        fields = ("id", "section", "section_title", "question_count", "order")


class MockExamSerializer(serializers.ModelSerializer):
    """Пробный экзамен вместе с секциями.

    Секции пишутся вложенно: мок без секций собрать нельзя, а два запроса
    ради одной формы означали бы мок, наполовину заведённый при обрыве.
    """

    sections = MockSectionSerializer(many=True, required=False)

    class Meta:
        model = MockExam
        fields = (
            "id",
            "title",
            "exam_type",
            "time_limit_minutes",
            "description",
            "is_active",
            "sections",
        )

    def create(self, validated_data):
        sections = validated_data.pop("sections", [])
        mock = MockExam.objects.create(**validated_data)
        for order, section in enumerate(sections, start=1):
            section.setdefault("order", order)
            MockSection.objects.create(mock=mock, **section)
        return mock

    def update(self, instance, validated_data):
        """Состав секций заменяется целиком: так его и правят — списком."""
        sections = validated_data.pop("sections", None)
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save()
        if sections is not None:
            instance.sections.all().delete()
            for order, section in enumerate(sections, start=1):
                section.setdefault("order", order)
                MockSection.objects.create(mock=instance, **section)
        return instance


class StartPracticeSerializer(serializers.Serializer):
    """Параметры тренировки."""

    exam_type = serializers.ChoiceField(choices=ExamType.choices)
    section = serializers.ChoiceField(choices=Section.choices, required=False, allow_blank=True)
    difficulty = serializers.ChoiceField(choices=Difficulty.choices, required=False, allow_blank=True)
    topic = serializers.CharField(required=False, allow_blank=True, max_length=120)
    size = serializers.IntegerField(required=False, min_value=1, max_value=50)


class AnswerSerializer(serializers.Serializer):
    """Ответ на одно задание. Верность считает сервер."""

    answer_id = serializers.IntegerField()
    option = serializers.IntegerField(required=False, allow_null=True)
    #: открытый ответ (Writing, Speaking): текст эссе или тезисы устного ответа
    text = serializers.CharField(required=False, allow_blank=True, max_length=20_000)
    seconds = serializers.IntegerField(required=False, min_value=0, max_value=36_000)


class FinishSerializer(serializers.Serializer):
    seconds = serializers.IntegerField(required=False, min_value=0, max_value=36_000)


class OpenAnswerReviewSerializer(serializers.Serializer):
    """Проверка открытого ответа руками: оценка по шкале экзамена и комментарий."""

    score = serializers.DecimalField(max_digits=4, decimal_places=1, min_value=0, required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=5_000)

    def validate(self, attrs):
        if attrs.get("score") is None and not str(attrs.get("comment") or "").strip():
            raise serializers.ValidationError("Нужна оценка или комментарий — пустую проверку ученик не поймёт")
        return attrs


class ReviewMockSerializer(serializers.Serializer):
    """Решение директора: учитывать платформенный мок или нет."""

    count_it = serializers.BooleanField()


class QuestionImportSerializer(serializers.Serializer):
    """Импорт банка заданий из файла."""

    file = serializers.FileField()


class TheoryLessonSerializer(serializers.ModelSerializer):
    """Урок теории (фаза 42). Файл отдаётся своим маршрутом с проверкой прав."""

    section_title = serializers.CharField(source="get_section_display", read_only=True, default="")
    level_title = serializers.CharField(source="get_level_display", read_only=True)
    has_file = serializers.SerializerMethodField()

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)

    class Meta:
        model = TheoryLesson
        fields = (
            "id",
            "exam_type",
            "section",
            "section_title",
            "title",
            "level",
            "level_title",
            "reading_minutes",
            "body",
            "has_file",
            "order",
            "is_active",
        )


# --- Квиз (фаза 46) --------------------------------------------------------
