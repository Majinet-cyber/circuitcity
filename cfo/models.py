from django.db import models
from django.conf import settings
from django.apps import apps


def BranchRefField(
    *,
    related_name: str | None = None,
    on_delete=None,
    null: bool = True,
    blank: bool = True,
    help_text: str | None = None,
):
    """
    Returns a ForeignKey to settings.BRANCH_MODEL if that model exists & the app is installed.
    Otherwise returns a CharField as a graceful fallback (so system checks don't fail).
    """
    model_path = getattr(settings, "BRANCH_MODEL", "").strip()
    if model_path:
        try:
            app_label = model_path.split(".")[0]
            if apps.is_installed(app_label):
                # Raises LookupError if not present
                apps.get_model(model_path)
                return models.ForeignKey(
                    model_path,
                    on_delete=on_delete or models.SET_NULL,
                    related_name=related_name,
                    null=null,
                    blank=blank,
                    help_text=help_text,
                )
        except LookupError:
            pass  # fall through to CharField

    # Fallback: store a branch identifier/name/code as text
    return models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=help_text or "Branch identifier (fallback text field when BRANCH_MODEL is unavailable).",
    )


class ExpenseCategory(models.Model):
    TYPE_CHOICES = (
        ("operational", "operational"),
        ("capital", "capital"),
        ("variable", "variable"),
    )
    name = models.CharField(max_length=120, unique=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="operational")
    is_personal = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.name


class Expense(models.Model):
    branch = BranchRefField(
        related_name="expenses",
        on_delete=models.CASCADE,
        help_text="FK to BRANCH_MODEL when available; otherwise a text identifier.",
    )
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="MWK")
    date = models.DateField()
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    receipt_url = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Budget(models.Model):
    branch = BranchRefField(
        related_name="budgets",
        on_delete=models.CASCADE,
        help_text="FK to BRANCH_MODEL when available; otherwise a text identifier.",
    )
    month = models.DateField(help_text="Use first day of month, e.g., 2025-09-01")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="budgets")
    limit_amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        unique_together = ("branch", "month", "category")


class CashLedger(models.Model):
    ENTRY_CHOICES = (("inflow", "inflow"), ("outflow", "outflow"), ("commit", "commit"))
    entry_type = models.CharField(max_length=10, choices=ENTRY_CHOICES)
    branch = BranchRefField(
        related_name="cash_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="FK to BRANCH_MODEL when available; otherwise a text identifier.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="MWK")
    date = models.DateField()
    ref_type = models.CharField(max_length=30)  # e.g., sale|salary|rent|supplier|expense|refund|transfer
    ref_id = models.CharField(max_length=64)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["date", "ref_type"])]


class PaymentIntent(models.Model):
    STATUS_CHOICES = (
        ("CREATED", "CREATED"),
        ("PENDING", "PENDING"),
        ("PAID", "PAID"),
        ("FAILED", "FAILED"),
    )
    PAYEE_CHOICES = (
        ("agent", "agent"),
        ("landlord", "landlord"),
        ("supplier", "supplier"),
    )
    payee_type = models.CharField(max_length=15, choices=PAYEE_CHOICES)
    payee_id = models.CharField(max_length=64)  # refer to your foreign key id; keep string for flexibility
    purpose = models.CharField(max_length=60)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="MWK")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="CREATED")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    external_ref = models.CharField(max_length=128, blank=True, null=True)
    meta = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="+", on_delete=models.SET_NULL, null=True, blank=True)


class ForecastSnapshot(models.Model):
    as_of_date = models.DateField()
    horizon_days = models.PositiveIntegerField(default=30)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2)
    projected_inflows = models.DecimalField(max_digits=14, decimal_places=2)
    projected_outflows = models.DecimalField(max_digits=14, decimal_places=2)
    projected_runway_days = models.PositiveIntegerField()
    method = models.CharField(max_length=40, default="moving_avg")
    params = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Alert(models.Model):
    KIND_CHOICES = (
        ("low_runway", "low_runway"),
        ("budget_overshoot", "budget_overshoot"),
        ("payroll_risk", "payroll_risk"),
        ("unusual_spend", "unusual_spend"),
        ("stockout_risk", "stockout_risk"),
    )
    SEVERITY = (("LOW", "LOW"), ("MEDIUM", "MEDIUM"), ("HIGH", "HIGH"))
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY, default="LOW")
    subject_type = models.CharField(max_length=30)  # branch|category|agent|supplier
    subject_id = models.CharField(max_length=64)
    message = models.TextField()
    state = models.CharField(max_length=10, default="OPEN")  # OPEN|ACK|RESOLVED
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


class Recommendation(models.Model):
    audience = models.CharField(max_length=10, default="admin")  # admin|agent|user
    audience_id = models.CharField(max_length=64, default="admin")
    title = models.CharField(max_length=160)
    body = models.TextField()
    rationale = models.TextField(blank=True, null=True)
    confidence = models.FloatField(default=0.6)
    action_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PersonalExpense(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="personal_expenses")
    category = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=8, default="MWK")
    date = models.DateField()
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
