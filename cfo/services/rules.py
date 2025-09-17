from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum
from ..models import Expense, Budget, Alert, ForecastSnapshot, CashLedger

def ensure_alert(kind, severity, subject_type, subject_id, message):
    return Alert.objects.create(kind=kind, severity=severity, subject_type=subject_type, subject_id=str(subject_id), message=message)

def run_rules():
    today = date.today()

    # Rule 1: Low runway
    snap = ForecastSnapshot.objects.order_by("-created_at").first()
    if snap and snap.projected_runway_days < 30:
        ensure_alert("low_runway","HIGH","global","0", f"Low runway: {snap.projected_runway_days} days")

    # Rule 2: Budget overshoot (this month)
    month_start = today.replace(day=1)
    exp = Expense.objects.filter(date__gte=month_start).values("branch","category").annotate(total=Sum("amount"))
    budgets = {(b.branch_id, b.category_id): b for b in Budget.objects.filter(month=month_start)}
    for row in exp:
        key = (row["branch"], row["category"])
        b = budgets.get(key)
        if b and row["total"] > b.limit_amount:
            ensure_alert("budget_overshoot","MEDIUM","branch", row["branch"], f"Budget overshoot for category {row['category']} by {row['total'] - b.limit_amount}")

    # Rule 3: Unusual spend (today vs 14-day avg)
    last_14 = today - timedelta(days=14)
    today_total = Expense.objects.filter(date=today).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    avg_14 = (Expense.objects.filter(date__gte=last_14, date__lt=today).aggregate(s=Sum("amount"))["s"] or Decimal("0")) / Decimal("14")
    if avg_14 and today_total > (avg_14 * Decimal("2.0")):
        ensure_alert("unusual_spend","MEDIUM","global","0", f"Unusual spend today: {today_total} vs avg {avg_14}")

    # Rule 4 (optional): Payroll risk – simplistic example
    # Assume there is a "commit" total for upcoming payroll this month
    commits = CashLedger.objects.filter(entry_type="commit", ref_type="salary", date__gte=month_start).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    opening = snap.opening_balance if snap else Decimal("0")
    if opening < commits:
        ensure_alert("payroll_risk","HIGH","global","0", f"Projected opening balance < payroll commitments: {opening} < {commits}")
