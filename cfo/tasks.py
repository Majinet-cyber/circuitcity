from celery import shared_task
from decimal import Decimal
from django.conf import settings
from .services.forecast import compute_forecast
from .services.rules import run_rules
from .services.recommend import recommend_affordability

@shared_task
def nightly_cfo_cycle():
    # opening balance: you may compute from last ledger balance; start simple:
    opening = Decimal(getattr(settings, "CFO_OPENING_BALANCE_DEFAULT", "0"))
    compute_forecast(horizon_days=30, opening_balance=opening)
    run_rules()
    recommend_affordability()


