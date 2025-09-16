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


# ------------------------------
# Views
# ------------------------------
@login_required
def sim_home(request: HttpRequest) -> HttpResponse:
    # Prefetch latest run for quick “last updated” display if desired
    scenarios = (
        Scenario.objects.filter(owner=request.user)
        .order_by("-created_at", "-id")
        .prefetch_related("runs")
    )
    return render(request, "simulator/home.html", {"scenarios": scenarios})


@login_required
def sim_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ScenarioForm(request.POST)
        if form.is_valid():
            scenario = form.save(commit=False)
            scenario.owner = request.user
            scenario.save()
            messages.success(request, "Scenario created.")
            return redirect("simulator:detail", pk=scenario.pk)
        else:
            messages.error(request, "Please fix the errors and try again.")
    else:
        form = ScenarioForm()
    return render(request, "simulator/new.html", {"form": form})


@login_required
def sim_detail(request: HttpRequest, pk: int) -> HttpResponse:
    scenario = get_object_or_404(Scenario, pk=pk, owner=request.user)
    latest = scenario.runs.order_by("-created_at", "-id").first()
    return render(
        request,
        "simulator/detail.html",
        {"scenario": scenario, "latest": latest},
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
    ):
        if key in request.POST:
            val = request.POST.get(key)
            try:
                overrides[key] = int(val) if key in ("baseline_monthly_units", "months") else float(val)
            except Exception:
                # Ignore bad overrides; fallback to scenario value
                pass

    payload = _scenario_payload(scenario)
    payload.update(overrides)

    # Compute
    results = run_deterministic(payload)

    # Persist run (supports results_json or legacy result_json)
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
def sim_compare(request: HttpRequest) -> HttpResponse:
    """
    Compare multiple scenarios side-by-side.
    - Accepts multiple ?id= query params (e.g. /simulator/compare/?id=1&id=2&id=3)
    - Returns HTML by default, JSON if requested/accepted.
    """
    raw_ids: List[str] = request.GET.getlist("id")
    # Sanitize and cap to 8 scenarios
    ids = [i for i in raw_ids if i.isdigit()][:8]

    if not ids:
        if _wants_json(request):
            return JsonResponse(
                {"ok": False, "error": "Provide at least one ?id= in the query string"},
                status=400,
            )
        return HttpResponseBadRequest("Provide ?id=1&id=2 to compare")

    qs = Scenario.objects.filter(owner=request.user, pk__in=ids).order_by("name", "pk")

    payload: List[Dict[str, Any]] = []
    for s in qs:
        data = _scenario_payload(s)
        res = run_deterministic(data)
        payload.append(
            {
                "scenario_id": s.id,
                "scenario_name": s.name,
                "results": res,
            }
        )

    if _wants_json(request):
        return JsonResponse({"ok": True, "items": payload}, status=200)

    return render(request, "simulator/compare.html", {"payload": payload})
