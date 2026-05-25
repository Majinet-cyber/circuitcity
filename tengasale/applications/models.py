from decimal import Decimal

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from deals.models import DeviceDeal


class FinancingApplication(models.Model):
    phone_validator = RegexValidator(r"^\d{9}$", "Phone number must be exactly 9 digits.")
    national_id_validator = RegexValidator(
        r"^[A-Za-z0-9]{8}$",
        "National ID must be exactly 8 letters or numbers.",
    )

    STATUS_CHOICES = [
        ("started", "Start"),
        ("customer_details", "Customer Details"),
        ("device_selection", "Device Selection"),
        ("kyc", "KYC"),
        ("kyc_capture", "KYC Capture"),
        ("location_details", "Location Details"),
        ("work_details", "Work Details"),
        ("signature", "Signature"),
        ("correction_requested", "Correction Requested"),
        ("imei_required", "IMEI Required"),
        ("submitted", "Submitted"),
        ("under_review", "Under Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("completed", "Completed"),
    ]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    application_number = models.CharField(max_length=50, unique=True, blank=True)

    customer_name = models.CharField(max_length=150, blank=True)
    customer_phone = models.CharField(max_length=9, blank=True, validators=[phone_validator])
    national_id = models.CharField(max_length=8, blank=True, validators=[national_id_validator])
    occupation = models.CharField(max_length=150, blank=True)
    income_band = models.CharField(max_length=40, blank=True)
    exact_monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    income_source = models.CharField(max_length=150, blank=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    location = models.CharField(max_length=150, blank=True)

    deal = models.ForeignKey(DeviceDeal, on_delete=models.SET_NULL, null=True, blank=True)
    selected_cash_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    selected_deposit_percent = models.DecimalField(max_digits=5, decimal_places=2, default=13)
    selected_loan_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("2.5"))
    calculated_total_loan = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_deposit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_monthly_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_daily_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_6_month_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_6_month_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_6_month_daily = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_3_month_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_3_month_monthly = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    calculated_3_month_daily = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    imei_number = models.CharField(max_length=80, blank=True)

    customer_face_image = models.ImageField(upload_to="kyc/faces/", blank=True, null=True)
    id_front_image = models.ImageField(upload_to="kyc/id_front/", blank=True, null=True)
    id_back_image = models.ImageField(upload_to="kyc/id_back/", blank=True, null=True)
    correction_customer_face_image = models.BooleanField(default=False)
    correction_id_front_image = models.BooleanField(default=False)
    correction_id_back_image = models.BooleanField(default=False)
    correction_notes = models.TextField(blank=True)

    region = models.CharField(max_length=30, blank=True)
    district = models.CharField(max_length=80, blank=True)
    traditional_authority = models.CharField(max_length=120, blank=True)
    precise_location = models.CharField(max_length=200, blank=True)
    map_screenshot = models.ImageField(upload_to="locations/maps/", blank=True, null=True)
    next_of_kin_1_name = models.CharField(max_length=150, blank=True)
    next_of_kin_1_phone = models.CharField(max_length=9, blank=True, validators=[phone_validator])
    next_of_kin_1_relationship = models.CharField(max_length=80, blank=True)

    work_description = models.TextField(blank=True)
    next_of_kin_2_name = models.CharField(max_length=150, blank=True)
    next_of_kin_2_phone = models.CharField(max_length=9, blank=True, validators=[phone_validator])
    next_of_kin_2_relationship = models.CharField(max_length=80, blank=True)
    proof_of_income_type = models.CharField(max_length=40, blank=True)
    proof_contact_name = models.CharField(max_length=150, blank=True)
    proof_contact_phone = models.CharField(max_length=9, blank=True, validators=[phone_validator])
    proof_notes = models.TextField(blank=True)

    signature_image = models.ImageField(upload_to="signatures/", blank=True, null=True)
    agreed_to_terms = models.BooleanField(default=False)

    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="started")

    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_applications",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)

    manager_comment = models.TextField(blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)

        if creating and not self.application_number:
            self.application_number = f"TSM-{timezone.now().strftime('%y%m%d')}-{self.pk:06d}"
            super().save(update_fields=["application_number"])

    def submit(self):
        self.status = "submitted"
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_at"])

    def get_continue_url(self):
        if self.status in ["started", "customer_details"]:
            return reverse("edit_customer_details", args=[self.id])

        if self.status == "device_selection":
            return reverse("choose_device", args=[self.id])

        if self.status in ["kyc", "kyc_capture", "correction_requested"]:
            return reverse("kyc_capture", args=[self.id])

        if self.status in ["location", "location_details"]:
            return reverse("location_details", args=[self.id])

        if self.status in ["work", "work_details"]:
            return reverse("work_details", args=[self.id])

        if self.status == "signature":
            return reverse("signature", args=[self.id])

        if self.status == "imei_required":
            return reverse("capture_imei", args=[self.id])

        return reverse("application_detail", args=[self.id])

    def apply_deal_selection(self, deal, selected_cash_price):
        self.deal = deal
        self.selected_cash_price = selected_cash_price
        self.selected_deposit_percent = deal.deposit_percent
        self.selected_loan_multiplier = deal.loan_multiplier
        self.calculated_total_loan = deal.calculated_total_loan(selected_cash_price)
        self.calculated_deposit_amount = deal.calculated_deposit(selected_cash_price)
        self.calculated_monthly_payment = deal.calculated_monthly_payment(selected_cash_price)
        self.calculated_daily_payment = deal.calculated_daily_payment(selected_cash_price)
        self.calculated_6_month_total = deal.calculated_6_month_total(selected_cash_price)
        self.calculated_6_month_monthly = deal.calculated_6_month_monthly(selected_cash_price)
        self.calculated_6_month_daily = deal.calculated_6_month_daily(selected_cash_price)
        self.calculated_3_month_total = deal.calculated_3_month_total(selected_cash_price)
        self.calculated_3_month_monthly = deal.calculated_3_month_monthly(selected_cash_price)
        self.calculated_3_month_daily = deal.calculated_3_month_daily(selected_cash_price)

    def __str__(self):
        return f"{self.application_number} - {self.customer_name}"
