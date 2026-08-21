"""Админка выпускников."""

from django.contrib import admin

from alumni.models import Alumnus, AlumnusApplication, ArchivedEssay, MentorshipMeeting, MentorshipRequest


class ApplicationInline(admin.TabularInline):
    model = AlumnusApplication
    extra = 0
    autocomplete_fields = ("program",)


@admin.register(Alumnus)
class AlumnusAdmin(admin.ModelAdmin):
    list_display = ("student", "graduation_year", "university", "country", "mentorship_consent")
    list_filter = ("graduation_year", "country", "mentorship_consent")
    search_fields = ("student__last_name", "student__first_name", "university__name")
    autocomplete_fields = ("student", "university", "program")
    inlines = [ApplicationInline]


class MeetingInline(admin.TabularInline):
    model = MentorshipMeeting
    extra = 0


@admin.register(MentorshipRequest)
class MentorshipRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "alumnus", "topic", "status", "is_visible_to_alumnus", "reviewed_by", "created_at")
    list_filter = ("status", "is_visible_to_alumnus")
    search_fields = ("student__last_name", "alumnus__student__last_name", "topic")
    inlines = [MeetingInline]


@admin.register(ArchivedEssay)
class ArchivedEssayAdmin(admin.ModelAdmin):
    list_display = ("title", "alumnus", "program", "consent_given", "is_anonymous", "created_at")
    list_filter = ("consent_given", "is_anonymous", "essay_type")
    search_fields = ("title", "alumnus__student__last_name")
    autocomplete_fields = ("alumnus", "program", "essay")
