import random
from decimal import Decimal

from django.conf import settings
from django.db import models


def generate_contract_number():
    for _ in range(100):
        number = "E" + "".join(random.choices("0123456789", k=8))
        if not Contract.objects.filter(contract_number=number).exists():
            return number
    raise RuntimeError("Could not generate a unique contract number.")


class Contract(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_TERMS_ACCEPTED = "terms_accepted"
    STATUS_SIGNED = "signed"
    STATUS_IMEI_ENTERED = "imei_entered"
    STATUS_CONTRACT_CREATED = "contract_created"
    STATUS_WARRANTY_CHECKED = "warranty_checked"
    STATUS_LOCKING = "locking"
    STATUS_LOCKED = "locked"
    STATUS_DEPOSIT_PENDING = "deposit_pending"
    STATUS_COMPLETE = "complete"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_TERMS_ACCEPTED, "Terms Accepted"),
        (STATUS_SIGNED, "Signed"),
        (STATUS_IMEI_ENTERED, "IMEI Entered"),
        (STATUS_CONTRACT_CREATED, "Contract Created"),
        (STATUS_WARRANTY_CHECKED, "Warranty Checked"),
        (STATUS_LOCKING, "Locking"),
        (STATUS_LOCKED, "Locked"),
        (STATUS_DEPOSIT_PENDING, "Deposit Pending"),
        (STATUS_COMPLETE, "Complete"),
    ]

    application = models.OneToOneField(
        "applications.FinancingApplication",
        on_delete=models.CASCADE,
        related_name="contract",
    )
    contract_number = models.CharField(max_length=9, unique=True, blank=True)
    merchant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contracts")
    customer_name = models.CharField(max_length=150)
    customer_phone = models.CharField(max_length=20, blank=True)
    national_id = models.CharField(max_length=20, blank=True)
    deal_name = models.CharField(max_length=200, blank=True)
    imei_number = models.CharField(max_length=15, blank=True)
    cash_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_loan = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    daily_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    terms_accepted_by_merchant = models.BooleanField(default=False)
    customer_contract_signature = models.ImageField(
        upload_to="contract_signatures/",
        blank=True,
        null=True,
    )
    customer_terms_accepted = models.BooleanField(default=False)
    warranty_checked = models.BooleanField(default=False)
    phone_locked = models.BooleanField(default=False)
    deposit_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.contract_number:
            self.contract_number = generate_contract_number()
        super().save(*args, **kwargs)

    @classmethod
    def from_application(cls, application):
        deal_name = str(application.deal) if application.deal_id else ""
        return cls.objects.get_or_create(
            application=application,
            defaults={
                "merchant": application.created_by,
                "customer_name": application.customer_name,
                "customer_phone": application.customer_phone,
                "national_id": application.national_id,
                "deal_name": deal_name,
                "cash_price": application.selected_cash_price or Decimal("0"),
                "total_loan": application.calculated_total_loan or Decimal("0"),
                "deposit_amount": application.calculated_deposit_amount or Decimal("0"),
                "monthly_payment": application.calculated_monthly_payment or Decimal("0"),
                "daily_payment": application.calculated_daily_payment or Decimal("0"),
            },
        )

    def __str__(self):
        return self.contract_number or f"Contract for {self.application_id}"

# Create your models here.
