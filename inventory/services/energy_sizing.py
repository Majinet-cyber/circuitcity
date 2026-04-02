# inventory/services/energy_sizing.py
"""
System sizing calculation engine for the Renewable Energy vertical.

This is the authoritative computation layer for all system sizing outputs.
All KPIs, recommendations, component sizes, and economic projections flow
from this single service — no duplicated logic across views or frontend.

[AI_HOOK] Replace heuristic pricing and efficiency curves with ML models.
"""
from __future__ import annotations

import logging
import math
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

D = Decimal
ZERO = D("0")
ONE = D("1")
HUNDRED = D("100")
THOUSAND = D("1000")


def _d(val, fallback: Decimal = ZERO) -> Decimal:
    if val is None:
        return fallback
    try:
        return D(str(val))
    except (InvalidOperation, ValueError):
        return fallback


def _pct(val: Decimal) -> Decimal:
    return val / HUNDRED


# ---------------------------------------------------------------------------
# Reference pricing (MWK) — [AI_HOOK] replace with live API / catalogue
# ---------------------------------------------------------------------------

PRICE_PER_PANEL_W = D("650")
PRICE_PER_BATTERY_KWH = D("450000")
PRICE_PER_INVERTER_KW = D("180000")
PRICE_PER_CHARGE_CONTROLLER_A = D("12000")
PRICE_PER_GENERATOR_KVA = D("120000")
INSTALLATION_FRACTION = D("0.15")
ANNUAL_MAINTENANCE_FRACTION = D("0.02")
SYSTEM_LIFETIME_YEARS = 25
GRID_TARIFF_PER_KWH = D("185")
DIESEL_KWH_PER_LITRE = D("3.0")


def compute_sizing(run) -> dict[str, Any]:
    """
    Run the full system sizing computation for a SystemSizingRun instance.
    Populates all computed fields and returns a summary dict.
    """
    appliances = list(run.appliances.all())
    if not appliances:
        return {"ok": False, "error": "No appliances/loads entered."}

    # ------------------------------------------------------------------
    # 1. Load analysis
    # ------------------------------------------------------------------
    total_daily_wh = sum((a.adjusted_daily_wh for a in appliances), ZERO)
    peak_load_w = sum((a.total_running_w for a in appliances), ZERO)
    surge_load_w = sum((a.total_surge_w for a in appliances), ZERO)

    critical_daily_wh = sum(
        (a.adjusted_daily_wh for a in appliances if a.is_critical), ZERO,
    )
    night_daily_wh = sum(
        (a.adjusted_daily_wh for a in appliances if a.usage_period in ("night", "both")), ZERO,
    )

    diversity = _d(run.diversity_factor, D("0.80"))
    simultaneity = _d(run.simultaneity_factor, D("0.70"))
    growth = ONE + _pct(_d(run.future_growth_pct, D("20")))
    safety = ONE + _pct(_d(run.safety_margin_pct, D("15")))

    corrected_demand_wh = total_daily_wh * diversity * growth * safety
    corrected_peak_w = peak_load_w * simultaneity * growth * safety

    run.total_daily_demand_wh = total_daily_wh.quantize(D("0.01"))
    run.total_daily_demand_kwh = (total_daily_wh / THOUSAND).quantize(D("0.01"))
    run.peak_load_w = peak_load_w.quantize(D("0.01"))
    run.surge_load_w = surge_load_w.quantize(D("0.01"))
    run.corrected_design_load_wh = corrected_demand_wh.quantize(D("0.01"))

    # ------------------------------------------------------------------
    # 2. Solar array sizing
    # ------------------------------------------------------------------
    psh = _d(run.peak_sun_hours, D("5.0"))
    panel_eff = _pct(_d(run.panel_efficiency_pct, D("85")))
    panel_wp = _d(run.panel_wattage, D("550"))

    if psh > ZERO and panel_eff > ZERO:
        array_wh_needed = corrected_demand_wh / panel_eff
        array_w = array_wh_needed / psh
        array_kw = (array_w / THOUSAND).quantize(D("0.01"), ROUND_HALF_UP)
        panel_count = int(math.ceil(float(array_w / panel_wp)))
    else:
        array_kw = ZERO
        panel_count = 0

    run.recommended_array_kw = array_kw
    run.recommended_panel_count = panel_count

    # ------------------------------------------------------------------
    # 3. Battery bank sizing
    # ------------------------------------------------------------------
    autonomy = _d(run.autonomy_days, ONE)
    dod = _pct(_d(run.battery_dod_pct, D("80")))

    battery_wh_needed = corrected_demand_wh * autonomy
    if dod > ZERO:
        total_battery_wh = battery_wh_needed / dod
    else:
        total_battery_wh = battery_wh_needed

    total_battery_kwh = (total_battery_wh / THOUSAND).quantize(D("0.01"))
    usable_kwh = (battery_wh_needed / THOUSAND).quantize(D("0.01"))

    run.recommended_battery_kwh = total_battery_kwh
    run.usable_storage_kwh = usable_kwh

    # ------------------------------------------------------------------
    # 4. Inverter sizing
    # ------------------------------------------------------------------
    inverter_w = corrected_peak_w
    if surge_load_w > inverter_w:
        inverter_w = surge_load_w * D("0.8")
    inverter_kw = (inverter_w / THOUSAND).quantize(D("0.01"), ROUND_HALF_UP)
    standard_sizes = [D("1"), D("3"), D("5"), D("8"), D("10"), D("15"), D("20"), D("30"), D("50")]
    for s in standard_sizes:
        if s >= inverter_kw:
            inverter_kw = s
            break
    else:
        inverter_kw = inverter_kw

    run.recommended_inverter_kw = inverter_kw
    if inverter_kw > ZERO:
        run.inverter_loading_pct = (
            (corrected_peak_w / THOUSAND) / inverter_kw * HUNDRED
        ).quantize(D("0.1"))
    else:
        run.inverter_loading_pct = ZERO

    # ------------------------------------------------------------------
    # 5. Charge controller
    # ------------------------------------------------------------------
    batt_v = _d(run.battery_voltage, D("48"))
    if batt_v > ZERO:
        cc_amps = ((array_kw * THOUSAND) / batt_v * D("1.25")).quantize(D("0.01"))
    else:
        cc_amps = ZERO
    run.recommended_charge_controller_a = cc_amps

    # ------------------------------------------------------------------
    # 6. Generator sizing (if selected)
    # ------------------------------------------------------------------
    if run.has_generator:
        gen_kva = (corrected_peak_w / THOUSAND / D("0.8")).quantize(D("0.01"))
        run.recommended_generator_kva = gen_kva
    else:
        run.recommended_generator_kva = None

    # ------------------------------------------------------------------
    # 7. Runtime estimate
    # ------------------------------------------------------------------
    if peak_load_w > ZERO and usable_kwh > ZERO:
        runtime_h = (usable_kwh * THOUSAND / peak_load_w).quantize(D("0.1"))
        run.estimated_runtime_hours = runtime_h
    else:
        run.estimated_runtime_hours = None

    # ------------------------------------------------------------------
    # 8. Economic analysis
    # ------------------------------------------------------------------
    capex_panels = panel_count * panel_wp * PRICE_PER_PANEL_W
    capex_battery = total_battery_kwh * PRICE_PER_BATTERY_KWH
    capex_inverter = inverter_kw * PRICE_PER_INVERTER_KW
    capex_cc = cc_amps * PRICE_PER_CHARGE_CONTROLLER_A
    capex_gen = ZERO
    if run.has_generator and run.recommended_generator_kva:
        capex_gen = run.recommended_generator_kva * PRICE_PER_GENERATOR_KVA

    total_capex = capex_panels + capex_battery + capex_inverter + capex_cc + capex_gen
    install_cost = (total_capex * INSTALLATION_FRACTION).quantize(D("0.01"))
    annual_maint = (total_capex * ANNUAL_MAINTENANCE_FRACTION).quantize(D("0.01"))

    run.estimated_capex = total_capex.quantize(D("0.01"))
    run.estimated_installation_cost = install_cost
    run.estimated_annual_maintenance = annual_maint

    daily_kwh = run.total_daily_demand_kwh or ZERO
    monthly_kwh = daily_kwh * D("30")
    grid_savings = monthly_kwh * GRID_TARIFF_PER_KWH
    run.grid_savings_monthly = grid_savings.quantize(D("0.01"))
    run.projected_monthly_savings = grid_savings.quantize(D("0.01"))
    run.projected_annual_savings = (grid_savings * D("12")).quantize(D("0.01"))

    if run.has_generator:
        fuel_cost = _d(run.generator_fuel_cost_per_litre, D("3500"))
        lph = _d(run.generator_litres_per_hour, D("2.5"))
        gen_hours_offset = float(daily_kwh / D("3.0")) if daily_kwh > ZERO else 0
        diesel_offset = D(str(gen_hours_offset)) * lph * fuel_cost * D("30")
        run.diesel_offset_monthly = diesel_offset.quantize(D("0.01"))
        total_savings_monthly = grid_savings + diesel_offset
    else:
        run.diesel_offset_monthly = ZERO
        total_savings_monthly = grid_savings

    total_project = total_capex + install_cost
    annual_savings = total_savings_monthly * D("12")

    if annual_savings > ZERO:
        payback = total_project / annual_savings
        run.payback_years = payback.quantize(D("0.1"))
    else:
        run.payback_years = None

    lifetime_savings = annual_savings * D(str(SYSTEM_LIFETIME_YEARS))
    lifetime_cost = total_project + (annual_maint * D(str(SYSTEM_LIFETIME_YEARS)))
    run.lifetime_cost_estimate = lifetime_cost.quantize(D("0.01"))

    if lifetime_cost > ZERO:
        total_lifetime_kwh = daily_kwh * D("365") * D(str(SYSTEM_LIFETIME_YEARS))
        if total_lifetime_kwh > ZERO:
            run.cost_per_kwh = (lifetime_cost / total_lifetime_kwh).quantize(D("0.01"))

    if total_project > ZERO and lifetime_savings > ZERO:
        run.roi_pct = (
            ((lifetime_savings - lifetime_cost) / total_project * HUNDRED)
        ).quantize(D("0.1"))

    # ------------------------------------------------------------------
    # 9. Component summary
    # ------------------------------------------------------------------
    run.component_summary = {
        "panels": {"count": panel_count, "wattage_each": float(panel_wp), "total_kw": float(array_kw)},
        "battery": {"total_kwh": float(total_battery_kwh), "usable_kwh": float(usable_kwh), "voltage": int(batt_v)},
        "inverter": {"kw": float(inverter_kw), "loading_pct": float(run.inverter_loading_pct or 0)},
        "charge_controller": {"amps": float(cc_amps)},
        "generator": {"kva": float(run.recommended_generator_kva or 0)} if run.has_generator else None,
    }

    # ------------------------------------------------------------------
    # 10. Intelligent recommendations
    # ------------------------------------------------------------------
    recs = []
    warns = []

    if usable_kwh > ZERO and night_daily_wh > ZERO:
        night_kwh = night_daily_wh / THOUSAND
        if usable_kwh < night_kwh:
            warns.append(
                f"Battery bank ({float(usable_kwh):.1f} kWh usable) may be too small "
                f"for nighttime critical loads ({float(night_kwh):.1f} kWh)."
            )

    if run.inverter_loading_pct and run.inverter_loading_pct > D("85"):
        warns.append(
            f"Inverter loading is high ({float(run.inverter_loading_pct):.0f}%). "
            "Consider upsizing the inverter for headroom."
        )

    inductive_loads = [a for a in appliances if a.load_type == "inductive"]
    if inductive_loads:
        inductive_surge = sum((a.total_surge_w for a in inductive_loads), ZERO)
        if inductive_surge > corrected_peak_w * D("0.5"):
            warns.append(
                "High inductive surge loads (motors, pumps, welding) are driving "
                "inverter sizing disproportionately. Consider soft-start equipment."
            )

    if float(_d(run.future_growth_pct, ZERO)) >= 15:
        recs.append(
            f"Projected {run.future_growth_pct}% growth suggests sizing reserve is advisable. "
            "Current design includes this growth factor."
        )

    critical_loads = [a for a in appliances if a.is_critical]
    non_critical = [a for a in appliances if not a.is_critical]
    if critical_loads and non_critical:
        recs.append(
            "This site may benefit from splitting critical and non-critical circuits "
            "for better load management during outages."
        )

    obj = run.design_objective
    if obj == "lowest_cost":
        recs.append("Current design objective favors low cost but may reduce resilience under extended outages.")
    elif obj == "high_reliability":
        recs.append("High reliability configuration selected — system is oversized for maximum uptime.")
    elif obj == "off_grid":
        recs.append("Off-grid design requires careful autonomy planning. Consider seasonal sun-hour variations.")

    if run.payback_years and run.payback_years > D("8"):
        warns.append(
            f"Payback period is {float(run.payback_years):.1f} years, which is relatively long. "
            "Review whether a smaller, phased approach could improve economics."
        )

    if run.estimated_runtime_hours and run.estimated_runtime_hours < D("3"):
        warns.append(
            f"Battery runtime is only {float(run.estimated_runtime_hours):.1f} hours at full load. "
            "Consider increasing battery capacity or autonomy days."
        )

    if panel_count > 0:
        recs.append(f"Recommended: {panel_count}x {int(panel_wp)}W panels ({float(array_kw):.1f} kW array).")
    if total_battery_kwh > ZERO:
        recs.append(f"Battery bank: {float(total_battery_kwh):.1f} kWh total ({float(usable_kwh):.1f} kWh usable).")
    recs.append(f"Inverter: {float(inverter_kw):.0f} kW recommended.")

    run.recommendations = recs
    run.warnings = warns

    # ------------------------------------------------------------------
    # 11. Advanced financial analysis (Phase 2: NPV, IRR, sensitivity)
    # ------------------------------------------------------------------
    _compute_advanced_financials(run, total_project, annual_savings, annual_maint, total_battery_kwh)

    # ------------------------------------------------------------------
    # 12. Growth headroom & unmet load risk
    # ------------------------------------------------------------------
    if array_kw > ZERO and run.total_daily_demand_kwh:
        generation_potential = array_kw * psh * panel_eff
        headroom = ((generation_potential - run.total_daily_demand_kwh) / generation_potential * HUNDRED)
        run.growth_headroom_pct = max(headroom, ZERO).quantize(D("0.1"))
    else:
        run.growth_headroom_pct = ZERO

    if usable_kwh > ZERO and critical_daily_wh > ZERO:
        critical_kwh = critical_daily_wh / THOUSAND
        if usable_kwh < critical_kwh:
            unmet = ((critical_kwh - usable_kwh) / critical_kwh * HUNDRED).quantize(D("0.1"))
            run.unmet_load_risk_pct = min(unmet, HUNDRED)
        else:
            run.unmet_load_risk_pct = ZERO
    else:
        run.unmet_load_risk_pct = ZERO

    # ------------------------------------------------------------------
    # 13. Save
    # ------------------------------------------------------------------
    run.save()

    return {
        "ok": True,
        "daily_demand_kwh": float(run.total_daily_demand_kwh or 0),
        "peak_load_w": float(run.peak_load_w or 0),
        "array_kw": float(array_kw),
        "panels": panel_count,
        "battery_kwh": float(total_battery_kwh),
        "inverter_kw": float(inverter_kw),
        "capex": float(total_capex),
        "payback_years": float(run.payback_years) if run.payback_years else None,
        "npv": float(run.npv) if run.npv else None,
        "irr_pct": float(run.irr_pct) if run.irr_pct else None,
    }


# ---------------------------------------------------------------------------
# Advanced financial engine (Phase 2)
# ---------------------------------------------------------------------------

def _compute_advanced_financials(run, total_project, annual_savings, annual_maint, battery_kwh):
    """Compute NPV, IRR, and sensitivity analysis for a sizing run."""
    discount = _pct(_d(run.discount_rate_pct, D("10")))
    tariff_esc = _pct(_d(run.tariff_escalation_pct, D("5")))
    batt_replace_year = run.battery_replacement_year or 10
    batt_replace_cost = _d(run.battery_replacement_cost) or (battery_kwh * PRICE_PER_BATTERY_KWH * D("0.8"))

    # Build yearly cash flows
    cash_flows = [-float(total_project)]
    for year in range(1, SYSTEM_LIFETIME_YEARS + 1):
        escalated_savings = float(annual_savings) * (1 + float(tariff_esc)) ** year
        maint = float(annual_maint)
        replacement = float(batt_replace_cost) if year == batt_replace_year else 0
        net = escalated_savings - maint - replacement
        cash_flows.append(net)

    # NPV
    npv_val = D("0")
    for i, cf in enumerate(cash_flows):
        if i == 0:
            npv_val += D(str(cf))
        else:
            npv_val += D(str(cf)) / (ONE + discount) ** i
    run.npv = npv_val.quantize(D("0.01"))

    # IRR via bisection
    run.irr_pct = _compute_irr(cash_flows)

    # Battery replacement cost (store for display)
    run.battery_replacement_cost = batt_replace_cost.quantize(D("0.01"))

    # Sensitivity analysis: pessimistic / base / optimistic
    run.sensitivity_summary = _sensitivity_analysis(
        total_project, annual_savings, annual_maint, tariff_esc, discount, batt_replace_year, batt_replace_cost,
    )


def _compute_irr(cash_flows, max_iter=100, tolerance=0.0001):
    """IRR via bisection method. Returns Decimal percentage or None."""
    lo, hi = -0.5, 5.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        npv = sum(cf / (1 + mid) ** i for i, cf in enumerate(cash_flows))
        if abs(npv) < tolerance:
            return D(str(mid * 100)).quantize(D("0.01"))
        if npv > 0:
            lo = mid
        else:
            hi = mid
    mid = (lo + hi) / 2
    return D(str(mid * 100)).quantize(D("0.01"))


def _sensitivity_analysis(total_project, annual_savings, annual_maint, tariff_esc, discount, batt_yr, batt_cost):
    """Run sensitivity across pessimistic / base / optimistic scenarios."""
    results = {}
    scenarios = {
        "pessimistic": {"savings_mult": 0.8, "cost_mult": 1.2, "esc_adj": -0.02},
        "base": {"savings_mult": 1.0, "cost_mult": 1.0, "esc_adj": 0.0},
        "optimistic": {"savings_mult": 1.2, "cost_mult": 0.8, "esc_adj": 0.02},
    }
    for name, adj in scenarios.items():
        adj_savings = float(annual_savings) * adj["savings_mult"]
        adj_maint = float(annual_maint) * adj["cost_mult"]
        adj_esc = float(tariff_esc) + adj["esc_adj"]

        cash_flows = [-float(total_project)]
        for yr in range(1, SYSTEM_LIFETIME_YEARS + 1):
            s = adj_savings * (1 + adj_esc) ** yr
            m = adj_maint
            r = float(batt_cost) if yr == batt_yr else 0
            cash_flows.append(s - m - r)

        npv = sum(cf / (1 + float(discount)) ** i for i, cf in enumerate(cash_flows))
        lifetime_savings = sum(cash_flows[1:])
        payback = None
        cumulative = -float(total_project)
        for yr in range(1, len(cash_flows)):
            cumulative += cash_flows[yr]
            if cumulative >= 0:
                payback = yr
                break

        results[name] = {
            "npv": round(npv, 2),
            "lifetime_savings": round(lifetime_savings, 2),
            "payback_years": payback,
        }
    return results


# ---------------------------------------------------------------------------
# Scenario comparison engine (Phase 2)
# ---------------------------------------------------------------------------

def create_scenario_group(base_run, objectives=None):
    """
    Create multiple scenarios from a base sizing run for side-by-side comparison.
    Returns list of created runs.
    """
    import uuid
    group_id = f"SCN-{uuid.uuid4().hex[:8].upper()}"

    if objectives is None:
        objectives = [
            ("lowest_cost", "Low Cost"),
            ("balanced", "Balanced"),
            ("high_reliability", "High Reliability"),
        ]

    base_run.scenario_group = group_id
    base_run.scenario_label = "Original"
    base_run.save(update_fields=["scenario_group", "scenario_label"])

    created = [base_run]
    for obj_code, obj_label in objectives:
        clone = base_run.clone(new_title=f"{base_run.title} – {obj_label}")
        clone.design_objective = obj_code
        clone.scenario_group = group_id
        clone.scenario_label = obj_label
        clone.save(update_fields=["design_objective", "scenario_group", "scenario_label"])
        result = compute_sizing(clone)
        if result.get("ok"):
            created.append(clone)

    _recommend_best_scenario(created)
    return created


def _recommend_best_scenario(scenarios):
    """Flag the scenario with best balanced score as recommended."""
    best = None
    best_score = -999999
    for s in scenarios:
        if s.npv is None and s.roi_pct is None:
            continue
        score = float(s.npv or 0) * 0.4
        if s.payback_years and s.payback_years > 0:
            score += (1 / float(s.payback_years)) * 10000 * 0.3
        score += float(s.roi_pct or 0) * 0.3
        if score > best_score:
            best_score = score
            best = s

    if not best and scenarios:
        best = scenarios[0]

    for s in scenarios:
        s.is_recommended_scenario = (s.pk == best.pk) if best else False
        s.save(update_fields=["is_recommended_scenario"])


def get_scenario_comparison(group_id):
    """Retrieve all scenarios in a group with comparison data."""
    try:
        from inventory.models_energy import SystemSizingRun
    except ImportError:
        return []
    return list(SystemSizingRun.objects.filter(scenario_group=group_id).order_by("created_at"))
