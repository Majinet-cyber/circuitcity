# inventory/admin.py
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.db.models import F, DecimalField, ExpressionWrapper, Sum, Q
from django.utils import timezone

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

# ---- Optional Docs/Business documents (invoices/quotes) ----
Doc = _m("Doc") or _m("Document") or _m("BusinessDoc") or _m("OrderDoc")
DocItem = _m("DocItem") or _m("DocumentItem") or _m("BusinessDocItem") or _m("OrderDocItem")


# =====================================================================
#                            CORE MODELS
# =====================================================================

# ---------- Locations (with GPS) ----------
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "latitude", "longitude", "geofence_radius_m")
    list_filter = ("city",)
    search_fields = ("name", "city")
    fieldsets = (
        ("Basics", {"fields": ("name", "city")}),
        (
            "Geofence (optional)",
            {
                "fields": ("latitude", "longitude", "geofence_radius_m"),
                "description": "If set, time check-ins can be validated against this point and radius (meters).",
            },
        ),
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
        "imei",
        "product",
        "status",
        "current_location",
        "assigned_agent",
        "received_at",
        "order_price",
        "selling_price",
        "profit_display",
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
        qs = super().get_queryset(request).select_related("product", "current_location", "assigned_agent")
        # annotate profit server-side to avoid per-row Python property work
        return qs.annotate(
            _profit=ExpressionWrapper(F("selling_price") - F("order_price"), output_field=DecimalField(max_digits=12, decimal_places=2))
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
            audits.append(
                InventoryAudit(
                    item=item,
                    by_user=request.user,
                    # Use an allowed choice value; include the transfer note in details
                    action="UPDATE",
                    details=f"Assigned/transferred to {getattr(target, 'username', target.pk)} via admin action",
                )
            )
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
            audits.append(
                InventoryAudit(
                    item=item,
                    by_user=request.user,
                    action="UPDATE",
                    details="Unassigned from agent (returned to warehouse) via admin action",
                )
            )
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
        return (obj.details[:120] + "â€¦") if len(obj.details) > 120 else obj.details


# ---------- Time logs (GPS check-ins) ----------
class TimeLogAdmin(admin.ModelAdmin):
    list_display = ("user", "checkin_type", "logged_at", "location", "within_geofence", "distance_m", "accuracy_m")
    list_filter = ("checkin_type", "within_geofence", "location", "logged_at")
    search_fields = ("user__username", "note")
    date_hierarchy = "logged_at"
    ordering = ("-logged_at",)
    list_select_related = ("user", "location")
    autocomplete_fields = ("user", "location")
    fieldsets = (
        ("When & who", {"fields": ("user", "checkin_type", "logged_at", "note")}),
        (
            "Where",
            {
                "fields": ("location", "latitude", "longitude", "accuracy_m", "distance_m", "within_geofence"),
                "description": "distance_m/within_geofence are usually filled by the API.",
            },
        ),
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


# =====================================================================
#                     OPTIONAL: BUSINESS DOCS ADMIN
# =====================================================================
def _field_exists(model, name: str) -> bool:
    try:
        return any(getattr(f, "name", None) == name for f in model._meta.get_fields())
    except Exception:
        return False


def _get_any_attr(obj, *names, default=None):
    for n in names:
        if hasattr(obj, n):
            v = getattr(obj, n, None)
            if v is not None and v != "":
                return v
    return default


if Doc is not None:
    class DocItemInline(admin.TabularInline):
        model = DocItem
        extra = 0
        autocomplete_fields = tuple(n for n in ("product",) if DocItem and _field_exists(DocItem, n))
        fields = [n for n in ("product", "description", "qty", "unit_price", "line_total") if DocItem and _field_exists(DocItem, n)]
        readonly_fields = tuple(n for n in ("line_total",) if DocItem and _field_exists(DocItem, n))
        show_change_link = False

        def get_queryset(self, request):
            qs = super().get_queryset(request)
            # If line_total is not stored, annotate it
            if DocItem and _field_exists(DocItem, "unit_price") and _field_exists(DocItem, "qty") and not _field_exists(DocItem, "line_total"):
                return qs.annotate(line_total=ExpressionWrapper(F("unit_price") * F("qty"), output_field=DecimalField(max_digits=12, decimal_places=2)))
            return qs

    class DocAdmin(admin.ModelAdmin):
        """
        Flexible admin that adapts to your Doc fields (invoice/quotation).
        Works with a variety of field names:
          - type/kind/doc_type
          - status/state
          - reference/number
          - customer / customer_name / client_name
          - total/amount/grand_total (or computed from items)
        """
        inlines = [DocItemInline] if DocItem is not None else []
        date_hierarchy = next((f for f in ("created_at", "issued_at", "created", "date") if _field_exists(Doc, f)), None)
        ordering = ("-id",)

        # Basic columns (computed if missing)
        @admin.display(description="Reference")
        def ref_display(self, obj):
            return _get_any_attr(obj, "reference", "number", "code", default=f"#{getattr(obj, 'pk', '')}")

        @admin.display(description="Type")
        def type_display(self, obj):
            return _get_any_attr(obj, "type", "kind", "doc_type", default="DOC")

        @admin.display(description="Customer")
        def customer_display(self, obj):
            # Prefer related customer.name, else a string field
            cust = _get_any_attr(obj, "customer", "client", default=None)
            if cust and hasattr(cust, "name"):
                return getattr(cust, "name")
            return _get_any_attr(obj, "customer_name", "client_name", default="")

        @admin.display(description="Total")
        def total_display(self, obj):
            total = _get_any_attr(obj, "total", "amount", "grand_total", default=None)
            if total is not None:
                return total
            # Compute from items if possible
            try:
                items_rel = getattr(obj, "items", None) or getattr(obj, "docitem_set", None)
                if items_rel is not None:
                    agg = items_rel.all().aggregate(
                        s=Sum(
                            ExpressionWrapper(
                                (F("qty")) * (F("unit_price")),
                                output_field=DecimalField(max_digits=12, decimal_places=2),
                            )
                        )
                    )
                    return agg["s"] or Decimal("0.00")
            except Exception:
                pass
            return Decimal("0.00")

        list_display = (
            "ref_display",
            "type_display",
            "customer_display",
            "status",
            "total_display",
            "created_at_display",
            "due_date_display",
        )

        def created_at_display(self, obj):
            return _get_any_attr(obj, "created_at", "issued_at", "created", "date", default=None)

        created_at_display.short_description = "Created"

        def due_date_display(self, obj):
            return _get_any_attr(obj, "due_date", "valid_until", "expires_at", default=None)

        due_date_display.short_description = "Due"

        list_per_page = 50
        show_full_result_count = False
        list_select_related = True

        # Search across common fields
        def get_search_fields(self, request):
            fields = ["reference", "number", "code", "customer__name", "customer_name", "client_name"]
            return tuple(f for f in fields if _field_exists(Doc, f.split("__")[0]))

        # Filters that only include existing fields
        def get_list_filter(self, request):
            candidates = ["status", "type", "kind", "doc_type", "created_at", "issued_at"]
            return tuple(f for f in candidates if _field_exists(Doc, f))

        # Autocomplete common relations
        autocomplete_fields = tuple(f for f in ("customer",) if _field_exists(Doc, f))

        # ---- Actions ----
        actions = ("action_mark_sent", "action_mark_paid")

        @admin.action(description="Mark as sent (email/whatsapp)")
        def action_mark_sent(self, request, queryset):
            if not _field_exists(Doc, "status"):
                messages.info(request, "Status field not present on Doc; nothing changed.")
                return
            updated = queryset.update(status="SENT")
            messages.success(request, f"Marked {updated} document(s) as SENT.")

        @admin.action(description="Mark as PAID")
        def action_mark_paid(self, request, queryset):
            if not _field_exists(Doc, "status"):
                messages.info(request, "Status field not present on Doc; nothing changed.")
                return
            # Allow both invoices-only or anything
            updated = queryset.update(status="PAID")
            messages.success(request, f"Marked {updated} document(s) as PAID.")

        # Keep admin robust if totals are stored server-side after save
        readonly_fields = tuple(f for f in ("total", "grand_total", "amount") if _field_exists(Doc, f))

    # Register Docs if present
    try:
        admin.site.register(Doc, DocAdmin)
    except admin.sites.AlreadyRegistered:
        pass


# =====================================================================
#            Register everything (without @admin.register)
# =====================================================================
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


