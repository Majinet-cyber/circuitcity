"""
Merchant Administrator models.

MerchantKYC       — extended KYC details for a MerchantLead
MerchantChecklist — verification checklist completed by a Merchant Administrator
"""
from django.conf import settings
from django.db import models


class MerchantKYC(models.Model):
    """Full KYC information collected for a merchant lead."""

    lead = models.OneToOneField(
        "website.MerchantLead",
        on_delete=models.CASCADE,
        related_name="kyc",
    )
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merchant_kyc_collected",
    )

    # Owner identity
    national_id_number = models.CharField(max_length=50, blank=True)
    business_reg_number = models.CharField(max_length=100, blank=True)

    # Location
    region = models.CharField(max_length=100, blank=True)
    gps_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    gps_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    physical_address = models.TextField(blank=True)
    trading_area = models.CharField(max_length=200, blank=True)

    # Banking / payout
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_name = models.CharField(max_length=200, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    airtel_money_number = models.CharField(max_length=30, blank=True)
    tnm_mpamba_number = models.CharField(max_length=30, blank=True)

    # Document uploads
    business_certificate = models.FileField(upload_to="merchant_docs/certs/", blank=True, null=True)
    tax_certificate = models.FileField(upload_to="merchant_docs/tax/", blank=True, null=True)
    shop_photo_1 = models.ImageField(upload_to="merchant_docs/photos/", blank=True, null=True)
    shop_photo_2 = models.ImageField(upload_to="merchant_docs/photos/", blank=True, null=True)

    # Internal
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Merchant KYC"
        verbose_name_plural = "Merchant KYC Records"

    def __str__(self):
        return f"KYC: {self.lead.business_name}"


class MerchantChecklist(models.Model):
    """Verification checklist completed by a Merchant Administrator."""

    RECOMMEND_APPROVE = "approve"
    RECOMMEND_REJECT = "reject"
    RECOMMEND_ESCALATE = "escalate"
    RECOMMEND_PENDING = "pending"

    RECOMMENDATION_CHOICES = [
        (RECOMMEND_PENDING,  "Pending"),
        (RECOMMEND_APPROVE,  "Recommend Approval"),
        (RECOMMEND_REJECT,   "Recommend Rejection"),
        (RECOMMEND_ESCALATE, "Escalate to HQ"),
    ]

    lead = models.OneToOneField(
        "website.MerchantLead",
        on_delete=models.CASCADE,
        related_name="checklist",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merchant_checklists",
    )

    # Verification checks
    spoke_to_owner = models.BooleanField(null=True, blank=True, verbose_name="Did you speak to the owner?")
    shop_physically_traceable = models.BooleanField(null=True, blank=True, verbose_name="Is the shop physically traceable?")
    documents_verified = models.BooleanField(null=True, blank=True, verbose_name="Were documents verified?")
    bank_name_matches = models.BooleanField(null=True, blank=True, verbose_name="Does bank/mobile money name match owner/shop?")
    understands_settlement = models.BooleanField(null=True, blank=True, verbose_name="Does merchant understand TengaSale settlement rules?")
    understands_no_wht = models.BooleanField(null=True, blank=True, verbose_name="Does merchant understand no WHT applies to merchant payouts?")
    understands_fraud_consequences = models.BooleanField(null=True, blank=True, verbose_name="Does merchant understand fraud consequences?")
    approved_for_pilot = models.BooleanField(null=True, blank=True, verbose_name="Is merchant approved for pilot?")

    # Outcome
    recommendation = models.CharField(
        max_length=20,
        choices=RECOMMENDATION_CHOICES,
        default=RECOMMEND_PENDING,
    )
    notes = models.TextField(blank=True)
    site_visit_completed = models.BooleanField(default=False)
    site_visit_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Merchant Checklist"
        verbose_name_plural = "Merchant Checklists"

    def __str__(self):
        return f"Checklist: {self.lead.business_name} — {self.get_recommendation_display()}"

    @property
    def checks_passed(self):
        checks = [
            self.spoke_to_owner,
            self.shop_physically_traceable,
            self.documents_verified,
            self.bank_name_matches,
            self.understands_settlement,
            self.understands_no_wht,
            self.understands_fraud_consequences,
            self.approved_for_pilot,
        ]
        filled = [c for c in checks if c is not None]
        passed = [c for c in filled if c is True]
        return f"{len(passed)}/{len(checks)}"
