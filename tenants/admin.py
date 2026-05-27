# tenants/admin.py
from django.contrib import admin
from django.contrib import messages
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from .models import Business, Membership


# ---------------------------------------------------------------------------
# Inlines from the notifications app.
# Both models FK/O2O to Business, so they belong on BusinessAdmin —
# NOT on DailySummarySettingsAdmin (that wiring breaks admin.E202 because
# BusinessEmailRecipient.business points to Business, not DailySummarySettings).
# ---------------------------------------------------------------------------
from notifications.models import (
    BusinessEmailRecipient as _BusinessEmailRecipient,
    DailySummarySettings as _DailySummarySettings,
)


class DailySummarySettingsInline(admin.StackedInline):
    """One-to-one block: enabled toggle, send hour, timezone."""
    model = _DailySummarySettings
    extra = 0
    max_num = 1
    can_delete = False
    verbose_name = "Daily Summary Settings"
    verbose_name_plural = "Daily Summary Settings"
    fields = ("is_enabled", "send_hour", "timezone", "last_sent_date")
    readonly_fields = ("last_sent_date",)


class BusinessEmailRecipientInline(admin.TabularInline):
    """Many daily-summary recipients per business."""
    model = _BusinessEmailRecipient
    extra = 1
    fields = ("email", "name", "is_active")
    verbose_name = "Daily Summary Recipient"
    verbose_name_plural = "Daily Summary Recipients"


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "subdomain")
    inlines = [DailySummarySettingsInline, BusinessEmailRecipientInline]

    actions = ["reset_business_data"]

    def reset_business_data(self, request, queryset):
        """Reset business data (superuser only)."""
        if not request.user.is_superuser:
            self.message_user(request, "Only superusers can reset business data.", level=messages.ERROR)
            return

        from tenants.services.reset_business import reset_business_data

        count = 0
        for business in queryset:
            try:
                reset_business_data(business, initiated_by=request.user, keep_catalog=False)
                count += 1
            except Exception as e:
                self.message_user(request, f"Failed to reset {business.name}: {str(e)}", level=messages.ERROR)

        if count > 0:
            self.message_user(request, f"Successfully reset {count} business(es).", level=messages.SUCCESS)

    reset_business_data.short_description = "Reset business data (wipe sales/stock)"


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "business", "role", "status", "created_at", "_actions")
    list_filter = ("role", "status")
    search_fields = ("user__username", "business__name")
    actions = ["deactivate_memberships", "hard_delete_memberships"]

    def _actions(self, obj):
        """Show quick action links."""
        return "—"  # Actions available via bulk actions

    _actions.short_description = "Actions"

    def delete_view(self, request, object_id, extra_context=None):
        """
        Override delete_view to catch exceptions and show user-friendly messages.
        Never crashes the admin.
        """
        try:
            return super().delete_view(request, object_id, extra_context)
        except (ProtectedError, IntegrityError) as e:
            # Get the membership to show context
            try:
                membership = self.get_object(request, object_id)
                user_name = str(membership.user) if membership else "this user"
            except:
                user_name = "this user"

            # Determine the blocking reason
            if isinstance(e, ProtectedError):
                blocking_objects = getattr(e, "protected_objects", [])
                if blocking_objects:
                    obj_names = [str(obj) for obj in list(blocking_objects)[:3]]
                    reason = f"This user has related records: {', '.join(obj_names)}"
                    if len(blocking_objects) > 3:
                        reason += f" and {len(blocking_objects) - 3} more"
                else:
                    reason = "This user has related records that prevent deletion."
            else:
                reason = "Database integrity constraint prevents deletion."

            self.message_user(
                request,
                f"Cannot delete {user_name}. {reason} Use 'Deactivate membership' instead, or contact support for hard deletion.",
                level=messages.ERROR,
            )

            # Redirect back to changelist
            return HttpResponseRedirect(reverse("admin:tenants_membership_changelist"))
        except Exception as e:
            # Catch any other exception
            self.message_user(
                request, f"Deletion failed: {str(e)}. Use 'Deactivate membership' instead.", level=messages.ERROR
            )
            return HttpResponseRedirect(reverse("admin:tenants_membership_changelist"))

    def deactivate_memberships(self, request, queryset):
        """Safely deactivate memberships (primary removal method)."""
        count = 0
        for membership in queryset:
            if membership.status != "REJECTED":
                membership.status = "REJECTED"
                membership.save(update_fields=["status"])
                count += 1

        self.message_user(
            request,
            f"Deactivated {count} membership(s). Users can no longer access this business.",
            level=messages.SUCCESS,
        )

    deactivate_memberships.short_description = "Deactivate membership (remove from business)"

    def hard_delete_memberships(self, request, queryset):
        """Hard delete memberships (superuser only, reassigns references)."""
        if not request.user.is_superuser:
            self.message_user(request, "Only superusers can hard delete memberships.", level=messages.ERROR)
            return

        from tenants.services.membership_delete import hard_delete_membership

        count = 0
        errors = []
        for membership in queryset:
            try:
                hard_delete_membership(membership, initiated_by=request.user)
                count += 1
            except Exception as e:
                errors.append(f"{membership}: {str(e)}")

        if count > 0:
            self.message_user(request, f"Hard deleted {count} membership(s).", level=messages.SUCCESS)
        if errors:
            for error in errors[:5]:  # Show first 5 errors
                self.message_user(request, error, level=messages.ERROR)

    hard_delete_memberships.short_description = "Hard delete membership (superuser only)"
