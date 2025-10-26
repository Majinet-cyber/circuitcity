# simulator/views.py
from __future__ import annotations

from typing import Any, Dict, List

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import ScenarioForm
from .logic import run_deterministic
from .models import Scenario, SimulationRun


# ------------------------------
# Helpers
# ------------------------------
def _scenario_payload(s: Scenario) -> Dict[str, Any]:
    """
    Convert a Scenario model to the numeric payload expected by run_deterministic().
    Cast to primitive types to avoid Decimal/JSON issues.
    """
    return {
        "baseline_monthly_units": int(getattr(s, "baseline_monthly_units", 0) or 0),
        "avg_unit_price": float(getattr(s, "avg_unit_price", 0.0) or 0.0),
        "variable_cost_pct": float(getattr(s, "variable_cost_pct", 0.0) or 0.0),
        "monthly_fixed_costs": float(getattr(s, "monthly_fixed_costs", 0.0) or 0.0),
        "monthly_growth_pct": float(getattr(s, "monthly_growth_pct", 0.0) or 0.0),
        "months": int(getattr(s, "months", 12) or 12),
        # Optional knobs used by the engine if present:
        "tax_rate_pct": float(getattr(s, "tax_rate_pct", 0.0) or 0.0),
        "opening_cash": float(getattr(s, "opening_cash", 0.0) or 0.0),
    }


def _wants_json(request: HttpRequest) -> bool:
    """
    Lightweight content negotiation: if the request prefers JSON
    (AJAX/fetch) or explicitly asks for it (?format=json).
    """
    if request.GET.get("format") == "json":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept or "json" in accept


def _get_results_json(run: SimulationRun) -> Dict[str, Any]:
    """
    Access results payload on either `results_json` (new) or legacy `result_json`.
    """
    return getattr(run, "results_json", None) or getattr(run, "result_json", {}) or {}


def _create_run(scenario: Scenario, result: Dict[str, Any]) -> SimulationRun:
    """
    Persist a SimulationRun regardless of whether the model field is `results_json`
    or the legacy `result_json`.
    """
    field_name = "results_json" if hasattr(SimulationRun, "results_json") else "result_json"
    return SimulationRun.objects.create(**{"scenario": scenario, field_name: result})


def _parse_ids(request: HttpRequest, cap: int = 8) -> List[int]:
    """
    Accepts both repeated ?id=1&id=2 and a single comma-delimited ?ids=1,2,3.
    Returns a de-duplicated, numeric list capped to `cap`.
    """
    ids: List[str] = request.GET.getlist("id")
    if request.GET.get("ids"):
        ids.extend(x.strip() for x in request.GET["ids"].split(","))
    clean: List[int] = []
    for s in ids:
        if s and s.isdigit():
            clean.append(int(s))
    seen = set()
    ordered: List[int] = []
    for i in clean:
        if i not in seen:
            seen.add(i)
            ordered.append(i)
        if len(ordered) >= cap:
            break
    return ordered


# ------------------------------
# Views
# ------------------------------
@login_required
def sim_home(request: HttpRequest) -> HttpResponse:
    """
    Scenarios list for the current user (latest first).
    """
    scenarios = (
        Scenario.objects.filter(owner=request.user)
        .order_by("-created_at", "-id")
        .prefetch_related("runs")
    )
    return render(request, "simulator/home.html", {"scenarios": scenarios})


@login_required
def sim_new(request: HttpRequest) -> HttpResponse:
    """
    Create a new scenario.
    """
    if request.method == "POST":
        form = ScenarioForm(request.POST)
        if form.is_valid():
            scenario = form.save(commit=False)
            scenario.owner = request.user
            scenario.save()
            messages.success(request, "Scenario created.")
            return redirect("simulator:detail", pk=scenario.pk)
        messages.error(request, "Please fix the errors and try again.")
    else:
        form = ScenarioForm()
    return render(request, "simulator/new.html", {"form": form})


@login_required
def sim_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Scenario details with latest run (if any).
    """
    scenario = get_object_or_404(Scenario, pk=pk, owner=request.user)
    latest = scenario.runs.order_by("-created_at", "-id").first()

    # Provide a ready-to-embed dict for the template (avoid non-existent template filters)
    latest_payload = _get_results_json(latest) if latest else {}

    return render(
        request,
        "simulator/detail.html",
        {
            "scenario": scenario,
            "latest": latest,
            "latest_payload": latest_payload,
        },
    )


@login_required
@require_POST
def sim_run(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Run a simulation for the scenario.
    - If the request prefers JSON (AJAX/fetch), return the run result as JSON.
    - Otherwise, persist the run and redirect back to detail with a flash message.
    """
    scenario = get_object_or_404(Scenario, pk=pk, owner=request.user)

    # Allow ad-hoc overrides in POST without saving them to the Scenario
    overrides: Dict[str, Any] = {}
    for key in (
        "baseline_monthly_units",
        "avg_unit_price",
        "variable_cost_pct",
        "monthly_fixed_costs",
        "monthly_growth_pct",
        "months",
        "tax_rate_pct",
        "opening_cash",
    ):
        if key in request.POST:
            val = request.POST.get(key)
            try:
                if key in ("baseline_monthly_units", "months"):
                    overrides[key] = int(val)
                else:
                    overrides[key] = float(val)
            except Exception:
                pass  # ignore bad overrides; fallback to scenario value

    payload = _scenario_payload(scenario)
    payload.update(overrides)

    results = run_deterministic(payload)
    run = _create_run(scenario, results)

    if _wants_json(request):
        return JsonResponse(
            {"ok": True, "scenario_id": scenario.pk, "run_id": run.pk, "data": results},
            status=200,
        )

    messages.success(request, "Simulation run completed.")
    return redirect("simulator:detail", pk=scenario.pk)


@login_required
@require_GET
def sim_results_api(request: HttpRequest, pk: int) -> JsonResponse:
    """
    Returns the *latest* results for a scenario as JSON.
    """
    scenario = get_object_or_404(Scenario, pk=pk, owner=request.user)
    latest = scenario.runs.order_by("-created_at", "-id").first()
    if not latest:
        return JsonResponse({"ok": False, "error": "No run yet"}, status=404)
    return JsonResponse(
        {
            "ok": True,
            "scenario_id": scenario.pk,
            "scenario_name": scenario.name,
            "created_at": latest.created_at.isoformat(),
            "data": _get_results_json(latest),
        }
    )


@login_required
@require_GET
def sim_compare(request: HttpRequest) -> HttpResponse:
    """
    Compare multiple scenarios side-by-side.
    - Accepts multiple ?id= query params (e.g. /simulator/compare/?id=1&id=2&id=3)
      and/or a single comma-separated ?ids=1,2,3
    - Returns HTML by default, JSON if requested/accepted.
    """
    ids: List[int] = _parse_ids(request, cap=8)

    if not ids:
        if _wants_json(request):
            return JsonResponse(
                {"ok": False, "error": "Provide at least one ?id= (or ?ids=1,2,3) in the query string"},
                status=400,
            )
        return HttpResponseBadRequest("Provide ?id=1&id=2 (or ?ids=1,2,3) to compare")

    # Only fetch scenarios owned by this user; keep requested order
    scenarios_qs = Scenario.objects.filter(owner=request.user, pk__in=ids)
    scenarios_map: Dict[int, Scenario] = {s.pk: s for s in scenarios_qs}
    ordered: List[Scenario] = [scenarios_map[i] for i in ids if i in scenarios_map]

    if not ordered:
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": "No matching scenarios found"}, status=404)
        return HttpResponseBadRequest("No matching scenarios found")

    payload: List[Dict[str, Any]] = []
    for s in ordered:
        data = _scenario_payload(s)
        res = run_deterministic(data)
        payload.append(
            {
                "scenario_id": s.id,
                "scenario_name": s.name,
                "results": res,  # contains 'series' and 'kpis'
            }
        )

    if _wants_json(request):
        return JsonResponse({"ok": True, "items": payload}, status=200)

    return render(request, "simulator/compare.html", {"payload": payload})


