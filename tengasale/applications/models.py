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
        ("draft", "Draft"),
        ("started", "Start"),
        ("customer_details", "Customer Details"),
        ("device_selection", "Device Selection"),
        ("kyc", "KYC"),
        ("kyc_capture", "KYC Capture"),
        ("location", "Location"),
        ("location_details", "Location Details"),
        ("work", "Work"),
        ("work_details", "Work Details"),
        ("signature", "Signature"),
        ("submitted", "Submitted"),
        ("pending_review", "Pending Review"),
        ("under_review", "Under Review"),
        ("correction_requested", "Correction Requested"),
        ("resubmitted", "Resubmitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("contract_terms", "Contract Terms"),
        ("contract_signature", "Contract Signature"),
        ("imei_entry", "IMEI Entry"),
        ("contract_creating", "Contract Creating"),
        ("warranty_check", "Warranty Check"),
        ("locking", "Locking"),
        ("deposit_pending", "Deposit Pending"),
        ("contract_complete", "Contract Complete"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("imei_required", "IMEI Required"),
    ]

    MERCHANT_STATUS_LABELS = {
        "pending_review": "Pending Review",
        "under_review": "Under Review",
        "needs_edit": "Needs Edit",
        "approved": "Approved",
        "completed": "Completed",
        "rejected": "Rejected",
    }

    CORRECTION_FIELD_LABELS = {
        "customer_name": "Customer name",
        "national_id": "National ID",
        "customer_phone": "Customer phone",
        "occupation": "Occupation",
        "income_band": "Income band",
        "exact_monthly_income": "Exact monthly income",
        "selected_deal": "Selected deal",
        "selected_cash_price": "Selected cash price",
        "calculated_deposit_amount": "Calculated deposit amount",
        "customer_face_image": "Customer face image",
        "id_front_image": "ID front image",
        "id_back_image": "ID back image",
        "region": "Region",
        "district": "District",
        "traditional_authority": "Traditional authority",
        "precise_location": "Precise location",
        "map_screenshot": "Map screenshot",
        "next_of_kin_1_name": "Next of kin 1 name",
        "next_of_kin_1_phone": "Next of kin 1 phone",
        "next_of_kin_1_relationship": "Next of kin 1 relationship",
        "work_description": "Work description",
        "next_of_kin_2_name": "Next of kin 2 name",
        "next_of_kin_2_phone": "Next of kin 2 phone",
        "next_of_kin_2_relationship": "Next of kin 2 relationship",
        "proof_of_income_type": "Proof of income type",
        "proof_contact_name": "Proof contact name",
        "proof_contact_phone": "Proof contact phone",
        "proof_notes": "Proof notes",
        "customer_signature": "Customer signature",
        "agreed_to_terms": "Agreed to terms",
    }

    CORRECTION_FIELD_ORDER = list(CORRECTION_FIELD_LABELS.keys())

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
    correction_fields = models.JSONField(default=list, blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)

        if creating and not self.application_number:
            self.application_number = f"TSM-{timezone.now().strftime('%y%m%d')}-{self.pk:06d}"
            super().save(update_fields=["application_number"])

    def submit(self):
        self.status = "pending_review"
        self.submitted_at = timezone.now()
        self.claimed_by = None
        self.claimed_at = None
        self.correction_fields = []
        self.save(update_fields=["status", "submitted_at", "claimed_by", "claimed_at", "correction_fields"])

    @property
    def merchant_status_key(self):
        if self.status == "correction_requested":
            return "needs_edit"

        if self.status in ["contract_complete", "completed"]:
            return "completed"

        if self.status in ["submitted", "pending_review", "resubmitted"]:
            return "under_review" if self.claimed_by_id else "pending_review"

        if self.status == "under_review":
            return "under_review"

        if self.status in ["approved", "rejected"]:
            return self.status

        return self.status

    @property
    def merchant_status_label(self):
        return self.MERCHANT_STATUS_LABELS.get(self.merchant_status_key, self.get_status_display())

    def get_continue_url(self):
        if self.status == "approved":
            return reverse("contract_terms", args=[self.id])

        if self.status in ["contract_terms", "contract_signature"]:
            contract = getattr(self, "contract", None)
            if contract and self.status == "contract_signature":
                return reverse("contract_signature", args=[contract.id])
            return reverse("contract_terms", args=[self.id])

        if self.status == "imei_entry":
            contract = getattr(self, "contract", None)
            return reverse("contract_imei", args=[contract.id]) if contract else reverse("contract_terms", args=[self.id])

        if self.status in ["contract_creating", "warranty_check", "locking", "deposit_pending"]:
            contract = getattr(self, "contract", None)
            return reverse("contract_progress", args=[contract.id]) if contract else reverse("contract_terms", args=[self.id])

        if self.status in ["contract_complete", "completed"]:
            contract = getattr(self, "contract", None)
            return reverse("contract_detail", args=[contract.id]) if contract else reverse("application_detail", args=[self.id])

        if self.status in ["started", "customer_details"]:
            return reverse("edit_customer_details", args=[self.id])

        if self.status == "device_selection":
            return reverse("choose_device", args=[self.id])

        if self.status in ["kyc", "kyc_capture"]:
            return reverse("kyc_capture", args=[self.id])

        if self.status == "correction_requested":
            return reverse("application_corrections", args=[self.id])

        if self.status in ["location", "location_details"]:
            return reverse("location_details", args=[self.id])

        if self.status in ["work", "work_details"]:
            return reverse("work_details", args=[self.id])

        if self.status == "signature":
            return reverse("signature", args=[self.id])

        if self.status == "imei_required":
            return reverse("capture_imei", args=[self.id])

        return reverse("application_detail", args=[self.id])

    def get_correction_start_url(self):
        page_map = {
            "customer": {
                "customer_name",
                "national_id",
                "customer_phone",
                "occupation",
                "income_band",
                "exact_monthly_income",
            },
            "device": {"selected_deal", "selected_cash_price", "calculated_deposit_amount"},
            "kyc": {"customer_face_image", "id_front_image", "id_back_image"},
            "location": {
                "region",
                "district",
                "traditional_authority",
                "precise_location",
                "map_screenshot",
                "next_of_kin_1_name",
                "next_of_kin_1_phone",
                "next_of_kin_1_relationship",
            },
            "work": {
                "work_description",
                "next_of_kin_2_name",
                "next_of_kin_2_phone",
                "next_of_kin_2_relationship",
                "proof_of_income_type",
                "proof_contact_name",
                "proof_contact_phone",
                "proof_notes",
            },
            "signature": {"customer_signature", "agreed_to_terms"},
        }
        fields = set(self.correction_fields or [])
        if fields & page_map["customer"]:
            return reverse("edit_customer_details", args=[self.id])
        if fields & page_map["device"]:
            return reverse("choose_device", args=[self.id])
        if fields & page_map["kyc"]:
            return reverse("kyc_capture", args=[self.id])
        if fields & page_map["location"]:
            return reverse("location_details", args=[self.id])
        if fields & page_map["work"]:
            return reverse("work_details", args=[self.id])
        if fields & page_map["signature"]:
            return reverse("signature", args=[self.id])
        return reverse("edit_customer_details", args=[self.id])

    def correction_field_labels(self):
        return [
            self.CORRECTION_FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())
            for field_name in self.correction_fields or []
        ]

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
