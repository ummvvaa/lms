from django.contrib import admin

from materials.models import (
    CollectionItem,
    MaterialCollection,
    MaterialComment,
    MaterialFile,
    MaterialReport,
    MaterialRequest,
    StudyMaterial,
)


class MaterialFileInline(admin.TabularInline):
    model = MaterialFile
    extra = 0


@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "subject", "source_kind", "status", "helpful_count", "created_at")
    list_filter = ("status", "source_kind", "subject")
    search_fields = ("title", "topic", "description")
    inlines = [MaterialFileInline]


@admin.register(MaterialComment)
class MaterialCommentAdmin(admin.ModelAdmin):
    list_display = ("material", "author", "created_at")
    search_fields = ("text",)


@admin.register(MaterialReport)
class MaterialReportAdmin(admin.ModelAdmin):
    list_display = ("id", "material", "comment", "reporter", "status", "created_at")
    list_filter = ("status",)


@admin.register(MaterialRequest)
class MaterialRequestAdmin(admin.ModelAdmin):
    list_display = ("topic", "subject", "author", "status", "created_at")
    list_filter = ("status", "subject")


class CollectionItemInline(admin.TabularInline):
    model = CollectionItem
    extra = 0


@admin.register(MaterialCollection)
class MaterialCollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "created_by", "created_at")
    inlines = [CollectionItemInline]
