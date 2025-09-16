# inventory/admin.py
from django.contrib import admin, messages
from django import forms
from django.db.models import F, DecimalField, ExpressionWrapper
from django.contrib.auth import get_user_model
from django.apps import apps

# ---- Resolve models lazily to avoid import-time errors during migrations ----
def _m(name):
    try:
        return apps.get_model("inventory", name)
    except Exception:
        return None

Location = _m("Location")
AgentProfile = _m("AgentProfile")
Product = _m("Product")
InventoryItem = _m("InventoryItem")
InventoryAudit = _m("InventoryAudit")
TimeLog = _m("TimeLog")
WalletTxn = _m("WalletTxn")
WarrantyCheckLog = _m("WarrantyCheckLog")
AgentPasswordReset = _m("AgentPasswordReset")
AuditLog = _m("AuditLog")  # proxy (optional)


# ---------- Locations (with GPS) ----------
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "latitude", "longitude", "geofence_radius_m")
    list_filter = ("city",)
    search_fields = ("name", "city")
    fieldsets = (
        ("Basics", {"fields": ("name", "city")}),
        ("Geofence (optional)", {
            "fields": ("latitude", "longitude", "geofence_radius_m"),
            "description": "If set, time check-ins can be validated against this point and radius (meters).",
        }),
    )
    ordering = ("name",)
    list_per_page = 50


# ---------- Agent profiles (with joined_on) ----------
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "location", "joined_on")
    list_filter = ("location", "joined_on")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    ordering = ("user__username",)
    fields = ("user", "location", "joined_on")
    list_select_related = ("user", "location")
    autocomplete_fields = ("user", "location")
    list_per_page = 50
    show_full_result_count = False  # big tables render faster


# ---------- Products ----------
class ProductAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "variant")
    list_filter = ("brand",)
    search_fields = ("model", "variant", "brand")
    ordering = ("brand", "model", "variant")
    list_per_page = 50


# ---------- Inventory + inline audits ----------
class InventoryAuditInline(admin.TabularInline):
    model = InventoryAudit
    extra = 0
    can_delete = False
    readonly_fields = ("action", "by_user", "at", "details")
    fields = ("at", "action", "by_user", "details")
    ordering = ("-at",)
    show_change_link = True
    verbose_name_plural = "Recent audits"


# ModelForm bound after models are available
class InventoryItemAdminForm(forms.ModelForm):
    """
    Admins may assign/transfer items but are NOT allowed to be the holder.
    This form enforces that 'assigned_agent' cannot be a staff/admin user.
    It also filters the autocomplete/queryset to non-staff users (i.e., field agents).
    """
    class Meta:
        model = InventoryItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        User = get_user_model()
        try:
            qs = User.objects.filter(is_staff=False)
        except Exception:
            qs = User.objects.none()
        if "assigned_agent" in self.fields:
            self.fields["assigned_agent"].queryset = qs
            self.fields["assigned_agent"].help_text = "Assign to a field agent (staff cannot hold stock)."

    def clean_assigned_agent(self):
        user = self.cleaned_data.get("assigned_agent")
        if user and getattr(user, "is_staff", False):
            raise forms.ValidationError("Staff/admin users cannot hold stock. Please choose a field agent.")
        return user


class AssignToAgentActionForm(forms.Form):
    """
    Extra widget shown above the actions dropdown to choose the target agent
    for the bulk transfer.
    """
    agent = forms.ModelChoiceField(
        queryset=get_user_model().objects.filter(is_staff=False),
        required=True,
        label="Target agent",
        help_text="Choose the agent who will receive the selected stock.",
    )


class InventoryItemAdmin(admin.ModelAdmin):
    form = InventoryItemAdminForm  # <- enforce 'admin cannot hold stock'

    # NOTE: profit is annotated in get_queryset for speed
    list_display = (
        "imei", "product", "status", "current_location", "assigned_agent",
        "received_at", "order_price", "selling_price", "profit_display",
    )
    list_filter = ("status", "current_location", "product__model", "product__brand")
    search_fields = ("imei", "product__model", "product__variant", "assigned_agent__username")
    date_hierarchy = "received_at"
    ordering = ("-received_at", "product__model")
    list_select_related = ("product", "current_location", "assigned_agent")
    autocomplete_fields = ("product", "current_location", "assigned_agent")
    inlines = [InventoryAuditInline]
    list_per_page = 50
    show_full_result_count = False

    # ----- Bulk actions -----
    actions = ("action_assign_to_agent", "action_unassign")
    action_form = AssignToAgentActionForm

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            "product", "current_location", "assigned_agent"
        )
        # annotate profit server-side to avoid per-row Python property work
        return qs.annotate(
            _profit=ExpressionWrapper(
                F("selling_price") - F("order_price"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )

    @admin.display(ordering="_profit", description="Profit")
    def profit_display(self, obj):
        return obj._profit

    @admin.action(description="Assign / transfer to selected agent")
    def action_assign_to_agent(self, request, queryset):
        """
        Bulk assign/transfer selected items to a non-staff agent.
        Writes an InventoryAudit entry for each item.
        """
        agent_id = request.POST.get("agent")
        if not agent_id:
            messages.warning(request, "Please pick a target agent in the action box, then click 'Go'.")
            return

        User = get_user_model()
        try:
            target = User.objects.get(pk=agent_id, is_staff=False)
        except User.DoesNotExist:
            messages.error(request, "Invalid target agent (staff/admin users cannot hold stock).")
            return

        # Perform update & audit trail
        updated = 0
        audits = []
        for item in queryset:
            # Skip if already assigned to the same target
            if item.assigned_agent_id == target.id:
                continue
            item.assigned_agent = target
            item.save(update_fields=["assigned_agent"])
            updated += 1
            audits.append(InventoryAudit(
                item=item,
                by_user=request.user,
                # Use an allowed choice value; include the transfer note in details
                action="UPDATE",
                details=f"Assigned/transferred to {getattr(target, 'username', target.pk)} via admin action",
            ))
        if audits:
            InventoryAudit.objects.bulk_create(audits, ignore_conflicts=True)

        messages.success(request, f"Transferred {updated} item(s) to {getattr(target, 'username', target.pk)}.")

    @admin.action(description="Unassign (return to warehouse)")
    def action_unassign(self, request, queryset):
        """
        Remove assigned agent (stock returns to warehouse pool).
        """
        updated = 0
        audits = []
        for item in queryset:
            if item.assigned_agent_id is None:
                continue
            item.assigned_agent = None
            item.save(update_fields=["assigned_agent"])
            updated += 1
            audits.append(InventoryAudit(
                item=item,
                by_user=request.user,
                action="UPDATE",
                details="Unassigned from agent (returned to warehouse) via admin action",
            ))
        if audits:
            InventoryAudit.objects.bulk_create(audits, ignore_conflicts=True)

        messages.success(request, f"Unassigned {updated} item(s).")


# ---------- Audit log ----------
class InventoryAuditAdmin(admin.ModelAdmin):
    list_display = ("at", "action", "item", "by_user", "short_details")
    list_filter = ("action", "at")
    search_fields = ("item__imei", "by_user__username", "details")
    date_hierarchy = "at"
    ordering = ("-at",)
    list_select_related = ("item", "by_user")
    list_per_page = 50
    show_full_result_count = False

    @admin.display(description="Details")
    def short_details(self, obj):
        if not obj.details:
            return ""
        return (obj.details[:120] + "…") if len(obj.details) > 120 else obj.details


# ---------- Time logs (GPS check-ins) ----------
class TimeLogAdmin(admin.ModelAdmin):
    list_display = ("user", "checkin_type", "logged_at", "location",
                    "within_geofence", "distance_m", "accuracy_m")
    list_filter = ("checkin_type", "within_geofence", "location", "logged_at")
    search_fields = ("user__username", "note")
    date_hierarchy = "logged_at"
    ordering = ("-logged_at",)
    list_select_related = ("user", "location")
    autocomplete_fields = ("user", "location")
    fieldsets = (
        ("When & who", {"fields": ("user", "checkin_type", "logged_at", "note")}),
        ("Where", {
            "fields": ("location", "latitude", "longitude", "accuracy_m", "distance_m", "within_geofence"),
            "description": "distance_m/within_geofence are usually filled by the API.",
        }),
    )
    readonly_fields = ("distance_m", "within_geofence")
    list_per_page = 50
    show_full_result_count = False


# ---------- Wallet transactions (advances/payouts/bonuses/commissions) ----------
class WalletTxnForm(forms.ModelForm):
    class Meta:
        model = WalletTxn
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["amount"].help_text = (
            "Positive = credit to agent (e.g., bonus, commission). "
            "Negative = deduction from agent (e.g., ADVANCE or PAYOUT)."
        )


class WalletTxnAdmin(admin.ModelAdmin):
    form = WalletTxnForm
    list_display = ("user", "amount", "reason", "created_at", "memo")
    list_filter = ("reason", "created_at")
    search_fields = ("user__username", "memo")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    fields = ("user", "amount", "reason", "created_at", "memo")
    list_per_page = 50
    show_full_result_count = False


# ---------- Warranty checks ----------
class WarrantyCheckLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "imei", "result", "expires_at", "item", "by_user")
    list_filter = ("result", "created_at")
    search_fields = ("imei", "item__imei", "by_user__username")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("item", "by_user")
    autocomplete_fields = ("item", "by_user")
    list_per_page = 50
    show_full_result_count = False


# ---------- Agent password reset ----------
class AgentPasswordResetAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "used", "created_at", "expires_at")
    list_filter = ("used", "created_at")
    search_fields = ("user__username", "code")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    list_per_page = 50
    show_full_result_count = False


# ---------- Register everything (without @admin.register to stay lazy) ----------
def _safe_register(model, admin_class):
    if model is None:
        return
    try:
        admin.site.register(model, admin_class)
    except admin.sites.AlreadyRegistered:
        pass

_safe_register(Location, LocationAdmin)
_safe_register(AgentProfile, AgentProfileAdmin)
_safe_register(Product, ProductAdmin)
_safe_register(InventoryItem, InventoryItemAdmin)
_safe_register(InventoryAudit, InventoryAuditAdmin)
_safe_register(TimeLog, TimeLogAdmin)
_safe_register(WalletTxn, WalletTxnAdmin)
_safe_register(WarrantyCheckLog, WarrantyCheckLogAdmin)
_safe_register(AgentPasswordReset, AgentPasswordResetAdmin)

# Optional: register AuditLog proxy if present
if AuditLog is not None:
    class AuditLogAdmin(InventoryAuditAdmin):
        pass
    _safe_register(AuditLog, AuditLogAdmin)
