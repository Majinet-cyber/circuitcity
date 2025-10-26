from django.contrib import admin
from . import models

def _first_attr(obj, names, default=None):
    """Return the first existing attribute from a list of names."""
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return default

# ----------------------------
# Scenario
# ----------------------------
@admin.register(models.Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    """
    Defensive admin that avoids crashes if your model uses slightly different
    field names (created vs created_at, months vs duration_months, etc.).
    """
    list_display = ("id", "name_display", "months", "created_display", "updated_display")
    search_fields = ("name", "title", "label")
    ordering = ("-id",)

    # --- columns ---
    def name_display(self, obj):
        return _first_attr(obj, ("name", "title", "label"), "(unnamed)")
    name_display.short_description = "Name"

    def months(self, obj):
        val = _first_attr(obj, ("months", "period_months", "duration_months"))
        return val if val is not None else "-"
    months.short_description = "Months"

    def created_display(self, obj):
        return _first_attr(obj, ("created", "created_at", "date_created"))
    created_display.short_description = "Created"

    def updated_display(self, obj):
        return _first_attr(obj, ("updated", "updated_at", "modified", "modified_at"))
    updated_display.short_description = "Updated"

# ----------------------------
# SimulationRun
# ----------------------------
@admin.register(models.SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    """
    Keeps columns generic and avoids referencing missing attrs.
    """
    list_display = ("id", "scenario_display", "status_display", "created_display", "duration_display")
    # Clear any invalid readonly fields to resolve admin.E035
    readonly_fields = ()
    ordering = ("-id",)

    def scenario_display(self, obj):
        # Prefer FK object if available
        scen = _first_attr(obj, ("scenario",), None)
        if scen is not None:
            # Show the scenario's name/title if present
            label = _first_attr(scen, ("name", "title", "label"), None)
            return label or str(scen)
        # Fallback: numeric FK id fields
        sid = _first_attr(obj, ("scenario_id",), None)
        return f"Scenario #{sid}" if sid is not None else "-"

    scenario_display.short_description = "Scenario"

    def status_display(self, obj):
        return _first_attr(obj, ("status", "state", "result_status"), "-")
    status_display.short_description = "Status"

    def created_display(self, obj):
        return _first_attr(obj, ("created", "created_at", "date_created"))
    created_display.short_description = "Created"

    def duration_display(self, obj):
        # Support seconds or milliseconds field names
        sec = _first_attr(obj, ("duration", "elapsed_seconds"), None)
        if sec is not None:
            return sec
        ms = _first_attr(obj, ("elapsed_ms",), None)
        if ms is not None:
            try:
                return round(ms / 1000.0, 3)
            except Exception:
                return ms
        return "-"
    duration_display.short_description = "Duration (s)"


