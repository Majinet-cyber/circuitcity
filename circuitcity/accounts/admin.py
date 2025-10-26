# accounts/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Profile, PasswordResetCode, LoginSecurity


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "user_email", "avatar_preview")
    search_fields = ("user__username", "user__email")
    list_select_related = ("user",)
    readonly_fields = ("user",)
    raw_id_fields = ("user",)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Email"

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html('<img src="{}" style="height:40px;width:40px;object-fit:cover;border-radius:50%;">', obj.avatar.url)
        return "â€”"
    avatar_preview.short_description = "Avatar"


@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "user_email",
        "created_at",
        "expires_at",
        "expired",
        "used",
        "attempts",
        "requester_ip",
    )
    list_select_related = ("user",)
    search_fields = ("user__email", "user__username", "requester_ip")
    list_filter = ("used",)
    date_hierarchy = "created_at"
    readonly_fields = ("code_hash", "created_at", "expires_at")
    raw_id_fields = ("user",)
    actions = ("mark_selected_used", "purge_selected_if_expired")

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Email"

    @admin.display(boolean=True, description="Expired")
    def expired(self, obj):
        return obj.is_expired()

    @admin.action(description="Mark selected codes as used")
    def mark_selected_used(self, request, queryset):
        updated = queryset.update(used=True)
        self.message_user(request, f"Marked {updated} code(s) as used.")

    @admin.action(description="Purge selected codes if expired & unused")
    def purge_selected_if_expired(self, request, queryset):
        now = timezone.now()
        qs = queryset.filter(used=False, expires_at__lt=now)
        deleted, _ = qs.delete()
        self.message_user(request, f"Purged {deleted} expired, unused code(s).")


@admin.register(LoginSecurity)
class LoginSecurityAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "user_email",
        "stage",
        "fail_count",
        "locked_until",
        "locked",
        "hard_blocked",
    )
    list_select_related = ("user",)
    search_fields = ("user__email", "user__username")
    list_filter = ("stage", "hard_blocked")
    raw_id_fields = ("user",)
    actions = ("unblock_selected_accounts",)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Email"

    @admin.display(boolean=True, description="Locked now")
    def locked(self, obj):
        return obj.is_locked()

    @admin.action(description="Unblock selected accounts (reset counters/locks)")
    def unblock_selected_accounts(self, request, queryset):
        updated = 0
        for sec in queryset:
            if sec.hard_blocked or sec.locked_until or sec.fail_count or sec.stage:
                sec.stage = 0
                sec.fail_count = 0
                sec.locked_until = None
                sec.hard_blocked = False
                sec.save(update_fields=["stage", "fail_count", "locked_until", "hard_blocked"])
                updated += 1
        self.message_user(request, f"Unblocked {updated} account(s).")


