# sales/views_commission.py
"""
Views for commission configuration (manager-only).
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from inventory.decorators import require_business
from inventory.verticals import base as inventory_base
from .models import CommissionConfig
from .forms import CommissionSettingsForm


@login_required
@require_business
@require_http_methods(["GET", "POST"])
def commission_settings(request):
    """
    Manager-only view to configure commission settings.
    Applies to future sales only (past sales keep their stored commission amounts).
    """
    ctx = inventory_base.base_context(request)
    business = ctx.get("business")

    # Check manager authorization
    if not ctx.get("is_manager"):
        messages.error(request, "Only managers can configure commission settings.")
        return redirect("inventory:inventory_dashboard")

    # Get or create commission config for this business
    config = CommissionConfig.ensure_config(business)

    if request.method == "POST":
        form = CommissionSettingsForm(request.POST, instance=config)
        if form.is_valid():
            # Save the config
            form.save()

            # Success message
            mode = form.cleaned_data.get("commission_mode")
            if mode == "percentage":
                pct = form.cleaned_data.get("base_commission_pct")
                messages.success(
                    request, f"✓ Commission settings updated! Agents will earn {pct}% commission on future sales."
                )
            else:
                amt = form.cleaned_data.get("fixed_commission_amount")
                messages.success(
                    request,
                    f"✓ Commission settings updated! Agents will earn {business.currency or 'MWK'} {amt:,.2f} per future sale.",
                )

            # Redirect back to agent performance page or referrer
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url:
                return redirect(next_url)

            # Fallback: redirect to agent performance
            return redirect("inventory:agent_performance")
    else:
        form = CommissionSettingsForm(instance=config)

    return render(
        request,
        "sales/commission_settings.html",
        {
            **ctx,
            "form": form,
            "config": config,
            "page_title": "Commission Settings",
        },
    )


@login_required
@require_business
def commission_settings_json(request):
    """
    JSON API endpoint to get current commission settings.
    Useful for async dashboard widgets.
    """
    from django.http import JsonResponse

    ctx = inventory_base.base_context(request)
    business = ctx.get("business")

    config = CommissionConfig.get_active(business)

    if not config:
        return JsonResponse(
            {
                "mode": "percentage",
                "percentage": "12.00",
                "fixed_amount": None,
            }
        )

    mode = "fixed" if config.fixed_commission_amount else "percentage"

    return JsonResponse(
        {
            "mode": mode,
            "percentage": str(config.base_commission_pct) if mode == "percentage" else "0.00",
            "fixed_amount": str(config.fixed_commission_amount) if config.fixed_commission_amount else None,
            "early_bonus_enabled": config.early_bonus_enabled,
            "early_bonus_per_30min": str(config.early_bonus_per_30min),
            "lateness_penalties_enabled": config.lateness_penalties_enabled,
            "late_penalty_per_30min": str(config.late_penalty_per_30min),
        }
    )
