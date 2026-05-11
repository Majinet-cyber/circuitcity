# backups/admin.py
from django.contrib import admin
from .models import BackupSnapshot, DataExportLog


@admin.register(BackupSnapshot)
class BackupSnapshotAdmin(admin.ModelAdmin):
    list_display = ["id", "business", "created_at", "status", "file_size_mb", "created_by"]
    list_filter = ["status", "created_at", "business"]
    search_fields = ["business__name", "created_by__username"]
    readonly_fields = ["created_at", "completed_at", "file_size", "records_count", "error_message"]
    date_hierarchy = "created_at"

    def file_size_mb(self, obj):
        return f"{obj.file_size_mb} MB" if obj.file_size else "—"

    file_size_mb.short_description = "File Size"


@admin.register(DataExportLog)
class DataExportLogAdmin(admin.ModelAdmin):
    list_display = ["id", "business", "category", "export_format", "status", "created_at", "user", "total_records"]
    list_filter = ["category", "export_format", "status", "created_at"]
    search_fields = ["business__name", "user__username", "user__email", "label"]
    readonly_fields = ["created_at", "records_count", "file_size", "snapshot"]
    date_hierarchy = "created_at"
