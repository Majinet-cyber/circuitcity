# sales/admin.py
from django.contrib import admin
from django.db.models import F, DecimalField, ExpressionWrapper
from .models import Sale


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "id", "item", "agent", "location",
        "sold_at", "price", "commission_pct", "commission",
        "created_at",
    )
    list_filter = ("location", "agent", "sold_at", "created_at")
    search_fields = ("item__imei", "agent__username")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    # Perf & UX
    list_select_related = ("item", "agent", "location")
    autocomplete_fields = ("item", "agent", "location")
    list_per_page = 50
    show_full_result_count = False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("item", "agent", "location")
        # annotate commission in SQL so the list isn’t computing it per row in Python
        commission_expr = ExpressionWrapper(
            F("price") * F("commission_pct") / 100.0,
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        return qs.annotate(_commission=commission_expr)

    @admin.display(ordering="_commission", description="Commission")
    def commission(self, obj):
        return obj._commission
