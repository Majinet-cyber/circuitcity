# hq/views_currency_settings.py
"""
HQ Admin views for managing global currency exchange rate settings.
"""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse

from hq.permissions import hq_admin_required
from core.models import ExchangeRate


@hq_admin_required
def currency_settings(request):
    """
    HQ Admin page to view and update the global MWK→USD exchange rate.
    GET: Show current rate and form to update
    POST: Update the rate (upsert singleton)
    """
    current_rate = ExchangeRate.get_current_rate()

    if request.method == "POST":
        mwk_per_usd_str = request.POST.get("mwk_per_usd", "").strip()

        if not mwk_per_usd_str:
            messages.error(request, "MWK per USD rate is required.")
            return render(
                request,
                "hq/currency_settings.html",
                {
                    "current_rate": current_rate,
                    "mwk_per_usd": mwk_per_usd_str,
                },
            )

        try:
            mwk_per_usd = Decimal(mwk_per_usd_str)
            if mwk_per_usd <= 0:
                messages.error(request, "Exchange rate must be greater than 0.")
                return render(
                    request,
                    "hq/currency_settings.html",
                    {
                        "current_rate": current_rate,
                        "mwk_per_usd": mwk_per_usd_str,
                    },
                )
        except (InvalidOperation, ValueError):
            messages.error(request, "Invalid exchange rate. Please enter a valid number.")
            return render(
                request,
                "hq/currency_settings.html",
                {
                    "current_rate": current_rate,
                    "mwk_per_usd": mwk_per_usd_str,
                },
            )

        # Upsert the singleton ExchangeRate
        if current_rate:
            current_rate.mwk_per_usd = mwk_per_usd
            current_rate.updated_by = request.user
            current_rate.save()
            messages.success(request, f"Exchange rate updated to {mwk_per_usd} MWK per USD.")
        else:
            ExchangeRate.objects.create(base="MWK", quote="USD", mwk_per_usd=mwk_per_usd, updated_by=request.user)
            messages.success(request, f"Exchange rate set to {mwk_per_usd} MWK per USD.")

        return redirect("hq:currency_settings")

    # GET request - show form
    return render(
        request,
        "hq/currency_settings.html",
        {
            "current_rate": current_rate,
            "mwk_per_usd": current_rate.mwk_per_usd if current_rate else None,
        },
    )
