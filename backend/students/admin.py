"""Админка учеников и справочника групп."""

from django.contrib import admin

from students.models import (
    Activity,
    AdmissionProfile,
    BehaviorProfile,
    Competition,
    ExamAttempt,
    ExamProfile,
    ParentContact,
    SportProfile,
    Student,
    StudyGroup,
    TalentProfile,
)


@admin.register(StudyGroup)
class StudyGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "grade", "curator", "student_count", "is_active")
    list_filter = ("grade", "is_active")
    search_fields = ("code", "curator")

    @admin.display(description="Учеников")
    def student_count(self, obj: StudyGroup) -> int:
        return obj.students.count()


class BehaviorInline(admin.StackedInline):
    model = BehaviorProfile
    can_delete = False
    extra = 0


class AdmissionInline(admin.StackedInline):
    model = AdmissionProfile
    can_delete = False
    extra = 0


class ExamInline(admin.StackedInline):
    model = ExamProfile
    can_delete = False
    extra = 0


class TalentInline(admin.StackedInline):
    model = TalentProfile
    can_delete = False
    extra = 0


class SportInline(admin.StackedInline):
    model = SportProfile
    can_delete = False
    extra = 0


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "grade", "group", "graduation_year", "is_active")
    list_filter = ("grade", "group", "graduation_year", "is_active")
    search_fields = ("last_name", "first_name", "email")
    autocomplete_fields = ("group", "user")
    inlines = [BehaviorInline, AdmissionInline, ExamInline, TalentInline, SportInline]


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "exam_type", "attempt_format", "date", "total_score")
    list_filter = ("exam_type", "attempt_format")
    search_fields = ("student__last_name", "student__first_name")
    autocomplete_fields = ("student",)


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("student", "category", "title", "date", "is_confirmed")
    list_filter = ("category", "is_confirmed")
    search_fields = ("student__last_name", "title")
    autocomplete_fields = ("student",)


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("student", "name", "date", "result", "has_certificate")
    list_filter = ("has_certificate",)
    search_fields = ("student__last_name", "name")
    autocomplete_fields = ("student",)


@admin.register(ParentContact)
class ParentContactAdmin(admin.ModelAdmin):
    list_display = ("student", "full_name", "relation", "phone", "email", "is_primary")
    list_filter = ("relation", "is_primary", "preferred_channel")
    search_fields = ("student__last_name", "full_name", "phone", "email")
    autocomplete_fields = ("student",)
