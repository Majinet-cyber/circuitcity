# inventory/admin.py
from django.contrib import admin
from django import forms
from django.db.models import F, DecimalField, ExpressionWrapper
from .models import (
    Location,
    AgentProfile,
    Product,
    InventoryItem,
    InventoryAudit,
    TimeLog,
    WalletTxn,
    WarrantyCheckLog,
    AgentPasswordReset,
)

# ---------- Locations (with GPS) ----------
@admin.register(Location)
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
@admin.register(AgentProfile)
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
@admin.register(Product)
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

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
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


# ---------- Audit log ----------
@admin.register(InventoryAudit)
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
@admin.register(TimeLog)
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

@admin.register(WalletTxn)
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
@admin.register(WarrantyCheckLog)
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
@admin.register(AgentPasswordReset)
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
