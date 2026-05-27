# hq/admin.py
from django.contrib import admin
from django.utils.html import format_html

from .models import HQPaymentMark, AgentMilestone, SupportTicket, SupportActionLog, MerchantContract
from .models_bugmonitor import SystemIssue, SystemIssueOccurrence, AdminAuditLog, IssueStatus, IssueSeverity


# ---------------------------------------------------------------------------
# Existing model admins
# ---------------------------------------------------------------------------

@admin.register(HQPaymentMark)
class HQPaymentMarkAdmin(admin.ModelAdmin):
    list_display = ["business", "period_start", "period_end", "amount", "marked_by", "marked_at"]
    list_filter  = ["period_start"]
    search_fields = ["business__name", "marked_by__username"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(AgentMilestone)
class AgentMilestoneAdmin(admin.ModelAdmin):
    list_display = ["user", "business", "milestone_type", "achieved_at"]
    list_filter  = ["milestone_type"]
    search_fields = ["user__username", "business__name"]


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display  = ["title", "business", "status", "priority", "created_by", "assigned_to", "created_at"]
    list_filter   = ["status", "priority"]
    search_fields = ["title", "business__name", "created_by__username"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(SupportActionLog)
class SupportActionLogAdmin(admin.ModelAdmin):
    list_display = ["action_type", "business", "performed_by", "created_at"]
    list_filter  = ["action_type"]
    search_fields = ["action_type", "business__name", "performed_by__username"]
    readonly_fields = ["created_at"]


@admin.register(MerchantContract)
class MerchantContractAdmin(admin.ModelAdmin):
    list_display  = ["title", "business", "contract_type", "signed_at", "uploaded_by"]
    list_filter   = ["contract_type"]
    search_fields = ["title", "business__name"]
    readonly_fields = ["uploaded_at", "updated_at"]


# ---------------------------------------------------------------------------
# Bug Monitor admins
# ---------------------------------------------------------------------------

_SEVERITY_COLORS = {
    IssueSeverity.LOW:      "#28a745",
    IssueSeverity.MEDIUM:   "#fd7e14",
    IssueSeverity.HIGH:     "#dc3545",
    IssueSeverity.CRITICAL: "#6f42c1",
}

_STATUS_COLORS = {
    IssueStatus.NEW:          "#dc3545",
    IssueStatus.INVESTIGATING: "#fd7e14",
    IssueStatus.CLEARED:      "#28a745",
    IssueStatus.IGNORED:      "#6c757d",
}


class SystemIssueOccurrenceInline(admin.TabularInline):
    model = SystemIssueOccurrence
    extra = 0
    max_num = 20
    readonly_fields = ["occurred_at", "path", "method", "user", "business", "ip_address"]
    fields = ["occurred_at", "path", "method", "user", "business", "ip_address"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SystemIssue)
class SystemIssueAdmin(admin.ModelAdmin):
    list_display = [
        "severity_badge", "status_badge", "title_short", "error_type",
        "status_code", "occurrence_count", "last_seen_at", "assigned_to",
    ]
    list_filter  = ["status", "severity", "status_code", "error_type"]
    search_fields = ["title", "error_type", "message", "path", "fingerprint"]
    readonly_fields = [
        "id", "fingerprint", "first_seen_at", "last_seen_at",
        "occurrence_count", "created_at", "updated_at",
        "cleared_by", "cleared_at",
    ]
    actions = ["mark_investigating", "mark_cleared", "mark_ignored"]
    inlines = [SystemIssueOccurrenceInline]

    fieldsets = [
        ("Classification", {
            "fields": ["id", "fingerprint", "title", "error_type", "message", "status_code", "severity", "status"],
        }),
        ("Request Context", {
            "fields": ["path", "method", "view_name", "app_label", "user", "business"],
        }),
        ("Device / Browser", {
            "fields": ["user_agent", "device_family", "browser_family", "os_family", "ip_address"],
            "classes": ["collapse"],
        }),
        ("Sanitized Payloads", {
            "fields": ["sanitized_get_params", "sanitized_post_data", "sanitized_payload"],
            "classes": ["collapse"],
        }),
        ("Stack Trace", {
            "fields": ["stack_trace"],
            "classes": ["collapse"],
        }),
        ("Recurrence", {
            "fields": ["occurrence_count", "first_seen_at", "last_seen_at"],
        }),
        ("Resolution", {
            "fields": ["assigned_to", "notes", "resolution_notes", "cleared_by", "cleared_at"],
        }),
        ("Environment", {
            "fields": ["environment", "release_version"],
            "classes": ["collapse"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]

    def severity_badge(self, obj):
        color = _SEVERITY_COLORS.get(obj.severity, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_severity_display(),
        )
    severity_badge.short_description = "Severity"

    def status_badge(self, obj):
        color = _STATUS_COLORS.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_status_display(),
        )
    status_badge.short_description = "Status"

    def title_short(self, obj):
        return obj.title[:80]
    title_short.short_description = "Title"

    @admin.action(description="Mark selected issues as Investigating")
    def mark_investigating(self, request, queryset):
        queryset.update(status=IssueStatus.INVESTIGATING)
        self.message_user(request, f"{queryset.count()} issues marked as Investigating.")

    @admin.action(description="Mark selected issues as Cleared")
    def mark_cleared(self, request, queryset):
        from django.utils import timezone
        queryset.update(
            status=IssueStatus.CLEARED,
            cleared_by=request.user,
            cleared_at=timezone.now(),
        )
        self.message_user(request, f"{queryset.count()} issues marked as Cleared.")

    @admin.action(description="Ignore selected issues")
    def mark_ignored(self, request, queryset):
        queryset.update(status=IssueStatus.IGNORED)
        self.message_user(request, f"{queryset.count()} issues ignored.")

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SystemIssueOccurrence)
class SystemIssueOccurrenceAdmin(admin.ModelAdmin):
    list_display = ["issue", "path", "method", "user", "occurred_at"]
    list_filter  = ["method"]
    search_fields = ["issue__title", "path", "user__username"]
    readonly_fields = [
        "id", "issue", "path", "method", "user", "business",
        "user_agent", "ip_address", "stack_trace",
        "sanitized_get_params", "sanitized_post_data", "sanitized_payload",
        "occurred_at", "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(AdminAuditLog)
class AdminAuditLogAdmin(admin.ModelAdmin):
    list_display = ["actor", "action", "target_model", "target_repr", "ip_address", "created_at"]
    list_filter  = ["action", "target_model"]
    search_fields = ["actor__username", "action", "target_repr", "target_id"]
    readonly_fields = [
        "id", "actor", "action", "target_model", "target_id", "target_repr",
        "before", "after", "metadata", "ip_address", "user_agent", "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
