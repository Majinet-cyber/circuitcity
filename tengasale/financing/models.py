import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    full_name = models.CharField(max_length=180)
    phone_number = models.CharField(max_length=30)
    customer_id_number = models.CharField("National ID / Customer ID", max_length=80)
    address = models.TextField(blank=True)
    next_of_kin_name = models.CharField(max_length=180, blank=True)
    next_of_kin_phone = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name


class Device(models.Model):
    STATUS_AVAILABLE = "available"
    STATUS_FINANCED = "financed"
    STATUS_LOCKED = "locked"
    STATUS_UNLOCKED = "unlocked"
    STATUS_COMPLETED = "completed"
    STATUS_DEFAULTED = "defaulted"

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_FINANCED, "Financed"),
        (STATUS_LOCKED, "Locked"),
        (STATUS_UNLOCKED, "Unlocked"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_DEFAULTED, "Defaulted"),
    ]

    brand = models.CharField(max_length=80)
    model = models.CharField(max_length=120)
    imei_1 = models.CharField(max_length=40, unique=True)
    imei_2 = models.CharField(max_length=40, blank=True)
    serial_number = models.CharField(max_length=80, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)
    assigned_customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["brand", "model", "imei_1"]

    def __str__(self):
        return f"{self.brand} {self.model} ({self.masked_imei})"

    @property
    def masked_imei(self):
        if len(self.imei_1) <= 6:
            return self.imei_1
        return f"{self.imei_1[:4]}****{self.imei_1[-4:]}"


class FinancingContract(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_OVERDUE = "overdue"
    STATUS_LOCKED = "locked"
    STATUS_COMPLETED = "completed"
    STATUS_DEFAULTED = "defaulted"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_OVERDUE, "Overdue"),
        (STATUS_LOCKED, "Locked"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_DEFAULTED, "Defaulted"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="financing_contracts")
    device = models.OneToOneField(Device, on_delete=models.PROTECT, related_name="financing_contract")
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_loan_amount = models.DecimalField(max_digits=12, decimal_places=2)
    monthly_payment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    term_months = models.PositiveIntegerField(default=6)
    start_date = models.DateField(default=timezone.localdate)
    next_due_date = models.DateField()
    lock_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_financing_contracts",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer.full_name} - {self.device}"

    @property
    def amount_due(self):
        schedule = self.repayment_schedule.exclude(status=RepaymentSchedule.STATUS_PAID)
        return sum((row.balance_due for row in schedule), start=0)

    @property
    def latest_unlock_token(self):
        return self.unlock_tokens.order_by("-created_at").first()

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating:
            previous = self.device.status
            self.device.assigned_customer = self.customer
            self.device.status = Device.STATUS_FINANCED
            self.device.save(update_fields=["assigned_customer", "status"])
            DeviceStatusLog.objects.create(
                device=self.device,
                contract=self,
                action=DeviceStatusLog.ACTION_ASSIGNED,
                status_before=previous,
                status_after=self.device.status,
                notes="Device assigned to financing contract.",
                created_by=self.created_by,
            )


class RepaymentSchedule(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PARTIALLY_PAID = "partially_paid"
    STATUS_PAID = "paid"
    STATUS_OVERDUE = "overdue"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PARTIALLY_PAID, "Partially Paid"),
        (STATUS_PAID, "Paid"),
        (STATUS_OVERDUE, "Overdue"),
    ]

    contract = models.ForeignKey(FinancingContract, on_delete=models.CASCADE, related_name="repayment_schedule")
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_date", "id"]

    def __str__(self):
        return f"{self.contract_id} due {self.due_date}"

    @property
    def balance_due(self):
        return max(self.amount_due - self.amount_paid, 0)


class PaymentRecord(models.Model):
    METHOD_CASH = "cash"
    METHOD_AIRTEL = "airtel_money"
    METHOD_TNM = "tnm_mpamba"
    METHOD_BANK = "bank_transfer"
    METHOD_OTHER = "other"

    METHOD_CHOICES = [
        (METHOD_CASH, "Cash"),
        (METHOD_AIRTEL, "Airtel Money"),
        (METHOD_TNM, "TNM Mpamba"),
        (METHOD_BANK, "Bank Transfer"),
        (METHOD_OTHER, "Other"),
    ]

    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_REJECTED = "rejected"

    VERIFICATION_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_REJECTED, "Rejected"),
    ]

    contract = models.ForeignKey(FinancingContract, on_delete=models.CASCADE, related_name="payments")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=METHOD_CHOICES, default=METHOD_CASH)
    transaction_reference = models.CharField(max_length=120, blank=True)
    proof_upload = models.FileField(upload_to="payment_proofs/", blank=True, null=True)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default=STATUS_PENDING)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_financing_payments",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer.full_name} MWK {self.amount}"


class DeviceStatusLog(models.Model):
    ACTION_REGISTERED = "registered"
    ACTION_ASSIGNED = "assigned"
    ACTION_PAYMENT_VERIFIED = "payment_verified"
    ACTION_UNLOCK_GENERATED = "unlock_generated"
    ACTION_LOCK_REQUESTED = "lock_requested"
    ACTION_UNLOCK_REQUESTED = "unlock_requested"
    ACTION_LOCKED = "locked"
    ACTION_UNLOCKED = "unlocked"
    ACTION_COMPLETED = "completed"

    ACTION_CHOICES = [
        (ACTION_REGISTERED, "Registered"),
        (ACTION_ASSIGNED, "Assigned"),
        (ACTION_PAYMENT_VERIFIED, "Payment Verified"),
        (ACTION_UNLOCK_GENERATED, "Unlock Generated"),
        (ACTION_LOCK_REQUESTED, "Lock Requested"),
        (ACTION_UNLOCK_REQUESTED, "Unlock Requested"),
        (ACTION_LOCKED, "Locked"),
        (ACTION_UNLOCKED, "Unlocked"),
        (ACTION_COMPLETED, "Completed"),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="status_logs")
    contract = models.ForeignKey(
        FinancingContract,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="device_status_logs",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    status_before = models.CharField(max_length=40, blank=True)
    status_after = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.device} - {self.action}"


class UnlockToken(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_USED = "used"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_USED, "Used"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REVOKED, "Revoked"),
    ]

    contract = models.ForeignKey(FinancingContract, on_delete=models.CASCADE, related_name="unlock_tokens")
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="unlock_tokens")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="unlock_tokens")
    token = models.CharField(max_length=20, unique=True, blank=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_unlock_tokens",
    )
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = generate_unlock_token()
        super().save(*args, **kwargs)

    @property
    def is_valid_now(self):
        now = timezone.now()
        return self.status == self.STATUS_ACTIVE and self.valid_from <= now <= self.valid_until

    def mark_used(self):
        self.status = self.STATUS_USED
        self.used_at = timezone.now()
        self.save(update_fields=["status", "used_at"])

    def __str__(self):
        return f"{self.contract_id} - {self.token}"


class DeviceCommand(models.Model):
    TYPE_REGISTER = "register"
    TYPE_LOCK = "lock"
    TYPE_UNLOCK = "unlock"
    TYPE_REFRESH_STATUS = "refresh_status"
    TYPE_DISABLE = "disable"
    TYPE_ENABLE = "enable"

    TYPE_CHOICES = [
        (TYPE_REGISTER, "Register"),
        (TYPE_LOCK, "Lock"),
        (TYPE_UNLOCK, "Unlock"),
        (TYPE_REFRESH_STATUS, "Refresh Status"),
        (TYPE_DISABLE, "Disable"),
        (TYPE_ENABLE, "Enable"),
    ]

    PROVIDER_MOCK = "mock"
    PROVIDER_TRUSTONIC = "trustonic"
    PROVIDER_UPYA = "upya"
    PROVIDER_ANDROID_MDM = "android_mdm"

    PROVIDER_CHOICES = [
        (PROVIDER_MOCK, "Mock"),
        (PROVIDER_TRUSTONIC, "Trustonic"),
        (PROVIDER_UPYA, "Upya"),
        (PROVIDER_ANDROID_MDM, "Android MDM"),
    ]

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_SUCCESSFUL = "successful"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_SUCCESSFUL, "Successful"),
        (STATUS_FAILED, "Failed"),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="commands")
    contract = models.ForeignKey(FinancingContract, on_delete=models.CASCADE, related_name="device_commands")
    command_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    provider = models.CharField(max_length=30, choices=PROVIDER_CHOICES, default=PROVIDER_MOCK)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.command_type} {self.device}"


def generate_unlock_token():
    for _ in range(100):
        token = "".join(secrets.choice("0123456789") for _ in range(6))
        if not UnlockToken.objects.filter(token=token).exists():
            return token
    return secrets.token_urlsafe(8)[:12]


def default_unlock_valid_until():
    return timezone.now() + timedelta(days=30)
