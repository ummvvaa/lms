"""Админка банка заданий и пробных экзаменов."""

from django.contrib import admin

from prep.models import MockExam, MockRun, MockSection, PracticeSession, Question, QuestionOption


class OptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4
    fields = ("letter", "text", "is_correct")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("topic", "exam_type", "section", "difficulty", "is_active")
    list_filter = ("exam_type", "section", "difficulty", "is_active")
    search_fields = ("topic", "text", "source")
    inlines = [OptionInline]


class SectionInline(admin.TabularInline):
    model = MockSection
    extra = 2
    fields = ("section", "question_count", "order")


@admin.register(MockExam)
class MockExamAdmin(admin.ModelAdmin):
    list_display = ("title", "exam_type", "time_limit_minutes", "is_active")
    list_filter = ("exam_type", "is_active")
    inlines = [SectionInline]


@admin.register(MockRun)
class MockRunAdmin(admin.ModelAdmin):
    """Только чтение: решение принимается в интерфейсе, а не здесь."""

    list_display = ("student", "mock", "counted_in_profile", "created_at")
    list_filter = ("counted_in_profile", "mock__exam_type")
    search_fields = ("student__last_name", "student__first_name")
    readonly_fields = ("student", "mock", "session", "exam_attempt", "reviewed_by", "reviewed_at", "created_at")

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = ("student", "exam_type", "section", "status", "started_at")
    list_filter = ("exam_type", "section", "status")
    readonly_fields = ("student", "started_at", "finished_at")

    def has_add_permission(self, request) -> bool:
        return False
