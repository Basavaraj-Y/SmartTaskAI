from django.contrib import admin

from core.models import Project, Task


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "deadline", "created_at")
    search_fields = ("name", "owner__email")
    filter_horizontal = ("members",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "assignee", "status", "priority", "due_date")
    list_filter = ("status", "priority")
    search_fields = ("title", "project__name", "assignee__email")
