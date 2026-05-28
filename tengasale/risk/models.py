"""
risk/models.py

Credit risk and identity models for TengaSale.
Supports credit scoring, identity profiling, external provider checks,
and device check readiness for Emajinet ID, warrant checks, and credit bureaus.
"""
import hashlib

from django.conf import settings
from django.db import models


class CustomerIdentityProfile(models.Model):
    VERIFICATION_PENDING = "pending"
    VERIFICATION_VERIFIED = "verified"
    VERIFICATION_FAILED = "failed"
    VERIFICATION_MANUAL = "manual"

    VERIFICATION_CHOICES = [
        (VERIFICATION_PENDING, "Pending"),
        (VERIFICATION_VERIFIED, "Verified"),
        (VERIFICATION_FAILED, "Failed"),
        (VERIFICATION_MANUAL, "Manual Review"),
    ]

    application = models.OneToOneField(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="identity_profile",
    )
    emajinet_id = models.CharField(max_length=80, blank=True, null=True)
    national_id_hash = models.CharField(max_length=64, blank=True)
    phone_hash = models.CharField(max_length=64, blank=True)
    verification_status = models.CharField(
        max_length=20, choices=VERIFICATION_CHOICES, default=VERIFICATION_PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Customer Identity Profile"

    def set_national_id_hash(self, national_id: str) -> None:
        self.national_id_hash = hashlib.sha256(national_id.strip().upper().encode()).hexdigest()

    def set_phone_hash(self, phone: str) -> None:
        digits = "".join(ch for ch in phone if ch.isdigit())
        self.phone_hash = hashlib.sha256(digits.encode()).hexdigest()

    def __str__(self):
        return f"IdentityProfile for {self.application_id}"


class CreditRiskAssessment(models.Model):
    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_MANUAL = "manual_review"

    RISK_CHOICES = [
        (RISK_LOW, "Low Risk"),
        (RISK_MEDIUM, "Medium Risk"),
        (RISK_HIGH, "High Risk"),
        (RISK_MANUAL, "Manual Review"),
    ]

    DEPOSIT_LOW = 15
    DEPOSIT_MEDIUM = 20
    DEPOSIT_HIGH = 30

    application = models.OneToOneField(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="credit_assessment",
    )

    affordability_score = models.IntegerField(default=0, help_text="Income vs repayment ratio score (0-100)")
    identity_score = models.IntegerField(default=0, help_text="KYC completeness and match score (0-100)")
    repayment_risk_score = models.IntegerField(default=0, help_text="Risk of non-repayment (0-100, higher = lower risk)")
    data_quality_score = models.IntegerField(default=0, help_text="Application completeness score (0-100)")
    final_score = models.IntegerField(default=0, help_text="Weighted final risk score (0-100)")
    risk_band = models.CharField(max_length=20, choices=RISK_CHOICES, default=RISK_MANUAL)
    recommended_deposit_percent = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    reasons = models.JSONField(
        default=list,
        help_text="List of human-readable reasons for this assessment",
    )
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_assessments_performed",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Credit Risk Assessment"

    @property
    def risk_band_label(self):
        return dict(self.RISK_CHOICES).get(self.risk_band, self.risk_band)

    @property
    def deposit_explanation(self):
        return (
            f"Recommended {self.recommended_deposit_percent}% deposit because: "
            + "; ".join(self.reasons or ["insufficient data for assessment"])
        )

    def __str__(self):
        return f"CreditRisk for app {self.application_id} — {self.risk_band}"


class ExternalCheck(models.Model):
    PROVIDER_EMAJINET = "emajinet_id"
    PROVIDER_WARRANT = "warrant_check"
    PROVIDER_CREDIT_BUREAU = "credit_bureau"
    PROVIDER_INTERNAL = "internal_history"

    PROVIDER_CHOICES = [
        (PROVIDER_EMAJINET, "Emajinet ID"),
        (PROVIDER_WARRANT, "Warrant Check"),
        (PROVIDER_CREDIT_BUREAU, "Credit Bureau"),
        (PROVIDER_INTERNAL, "Internal History"),
    ]

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    application = models.ForeignKey(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="external_checks",
    )
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    request_reference = models.CharField(max_length=120, blank=True)
    response_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "External Check"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.provider} for app {self.application_id} [{self.status}]"


class FraudCheck(models.Model):
    """
    Records a duplicate-customer / existing-exposure fraud check
    performed before or during underwriter review.
    """

    RISK_NONE = "none"
    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_BLOCK = "block"

    RISK_CHOICES = [
        (RISK_NONE, "No Risk"),
        (RISK_LOW, "Low Risk"),
        (RISK_MEDIUM, "Medium Risk"),
        (RISK_HIGH, "High Risk"),
        (RISK_BLOCK, "Block — Do Not Proceed"),
    ]

    ACTION_PROCEED = "proceed"
    ACTION_MANUAL = "manual_review"
    ACTION_HQ = "require_hq_approval"
    ACTION_BLOCK = "block_new_contract"

    ACTION_CHOICES = [
        (ACTION_PROCEED, "Proceed"),
        (ACTION_MANUAL, "Manual Review"),
        (ACTION_HQ, "Require HQ Approval"),
        (ACTION_BLOCK, "Block New Contract"),
    ]

    RESOLUTION_OPEN = "open"
    RESOLUTION_CLEARED = "cleared"
    RESOLUTION_BLOCKED = "blocked"
    RESOLUTION_HQ_OVERRIDE = "hq_override"

    RESOLUTION_CHOICES = [
        (RESOLUTION_OPEN, "Open"),
        (RESOLUTION_CLEARED, "Cleared"),
        (RESOLUTION_BLOCKED, "Blocked"),
        (RESOLUTION_HQ_OVERRIDE, "HQ Override"),
    ]

    application = models.ForeignKey(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="fraud_checks",
    )
    national_id_hash = models.CharField(max_length=64, blank=True, db_index=True)
    phone_hash = models.CharField(max_length=64, blank=True, db_index=True)
    result = models.JSONField(default=dict, blank=True)
    risk_level = models.CharField(max_length=10, choices=RISK_CHOICES, default=RISK_NONE)
    recommended_action = models.CharField(max_length=30, choices=ACTION_CHOICES, default=ACTION_PROCEED)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fraud_checks_performed",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fraud_checks_resolved",
    )
    resolution_status = models.CharField(max_length=20, choices=RESOLUTION_CHOICES, default=RESOLUTION_OPEN)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Fraud Check"
        ordering = ["-created_at"]

    @property
    def is_blocking(self):
        return self.risk_level in (self.RISK_HIGH, self.RISK_BLOCK)

    def __str__(self):
        return f"FraudCheck for app {self.application_id} — {self.risk_level}"


class DeviceCheck(models.Model):
    """
    Records a device authenticity / warranty / lock-eligibility check.
    Supports mock providers now; real provider integrations added later.
    """

    STATUS_PENDING = "pending"
    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PASSED, "Passed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    WARRANTY_VALID = "valid"
    WARRANTY_EXPIRED = "expired"
    WARRANTY_UNKNOWN = "unknown"

    WARRANTY_CHOICES = [
        (WARRANTY_VALID, "Valid"),
        (WARRANTY_EXPIRED, "Expired"),
        (WARRANTY_UNKNOWN, "Unknown"),
    ]

    PROVIDER_MOCK = "mock"
    PROVIDER_IMEI_DB = "imei_db"
    PROVIDER_MANUFACTURER = "manufacturer"

    PROVIDER_CHOICES = [
        (PROVIDER_MOCK, "Mock / Placeholder"),
        (PROVIDER_IMEI_DB, "IMEI Database"),
        (PROVIDER_MANUFACTURER, "Manufacturer API"),
    ]

    application = models.ForeignKey(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="device_checks",
        null=True,
        blank=True,
    )
    contract = models.ForeignKey(
        "portal.PaymentContract",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_checks",
    )
    imei = models.CharField(max_length=20, blank=True)
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default=PROVIDER_MOCK)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    warranty_status = models.CharField(max_length=20, choices=WARRANTY_CHOICES, default=WARRANTY_UNKNOWN)
    lock_eligible = models.BooleanField(default=False, help_text="Whether this device can be enrolled in PayG lock")
    response_summary = models.TextField(blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Device Check"
        ordering = ["-checked_at"]

    def __str__(self):
        return f"DeviceCheck IMEI={self.imei or '?'} [{self.status}] via {self.provider}"
