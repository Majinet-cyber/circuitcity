# insights/services_fx.py
from __future__ import annotations
import requests
from django.utils import timezone
from .models import CurrencySetting

API_URLS = [
    "https://api.exchangerate.host/latest",         # no key
    "https://open.er-api.com/v6/latest/{base}",     # no key
]

def update_rates(base: str | None = None) -> dict:
    cfg = CurrencySetting.get()
    base = (base or cfg.base_currency or "MWK").upper()
    rates: dict = {}

    # Try first API
    try:
        r = requests.get(API_URLS[0], params={"base": base}, timeout=8)
        if r.ok:
            data = r.json()
            rates = data.get("rates", {}) or {}
    except Exception:
        pass

    # Fallback API
    if not rates:
        try:
            r = requests.get(API_URLS[1].format(base=base), timeout=8)
            if r.ok:
                data = r.json()
                rates = data.get("rates", {}) or {}
        except Exception:
            pass

    if rates:
        cfg.base_currency = base
        cfg.rates = rates
        cfg.save(update_fields=["base_currency", "rates", "updated_at"])
    return rates
