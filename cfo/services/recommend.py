from decimal import Decimal
from ..models import Recommendation, ForecastSnapshot, CashLedger

def recommend_affordability(car_target=Decimal("8000000"), min_runway_days=30, safety_factor=Decimal("0.8")):
    snap = ForecastSnapshot.objects.order_by("-created_at").first()
    if not snap:
        return
    daily_out = (snap.projected_outflows / snap.horizon_days) if snap.horizon_days else Decimal("0")
    reserve = daily_out * Decimal(min_runway_days)
    surplus = (snap.opening_balance + snap.projected_inflows - snap.projected_outflows) - reserve
    safe_spend = max(Decimal("0"), surplus) * safety_factor

    title = "You can afford a car" if safe_spend >= car_target else "Not safe to buy a car yet"
    body = f"Safe discretionary: {safe_spend:.2f}. Reserve kept: {reserve:.2f}. Target: {car_target:.2f}."
    Recommendation.objects.create(audience="admin", audience_id="admin", title=title, body=body, rationale="affordability_v1", confidence=0.65)


