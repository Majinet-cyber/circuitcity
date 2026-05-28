"""Website models — lead capture for merchant signups and career applications."""
from django.db import models


class MerchantLead(models.Model):
    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_QUALIFIED = "qualified"
    STATUS_CONVERTED = "converted"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_QUALIFIED, "Qualified"),
        (STATUS_CONVERTED, "Converted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    BUSINESS_TYPE_CHOICES = [
        ("phone_shop", "Phone Shop"),
        ("electronics_shop", "Electronics Shop"),
        ("mixed_retail", "Mixed Retail"),
        ("agent", "Agent"),
        ("other", "Other"),
    ]

    PAYOUT_CHOICES = [
        ("bank", "Bank Transfer"),
        ("airtel_money", "Airtel Money"),
        ("tnm_mpamba", "TNM Mpamba"),
        ("not_sure", "Not sure yet"),
    ]

    business_name = models.CharField(max_length=200)
    owner_full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    whatsapp_phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    district = models.CharField(max_length=100)
    area = models.CharField(max_length=100, blank=True)
    business_type = models.CharField(max_length=30, choices=BUSINESS_TYPE_CHOICES)
    estimated_monthly_phone_sales = models.PositiveIntegerField(default=0)
    has_business_registration = models.BooleanField(null=True, blank=True)
    preferred_payout_method = models.CharField(max_length=20, choices=PAYOUT_CHOICES, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    assigned_to = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merchant_leads",
    )
    source = models.CharField(max_length=50, default="public_site")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Merchant Lead"
        verbose_name_plural = "Merchant Leads"

    def __str__(self):
        return f"{self.business_name} — {self.owner_full_name}"


class CareerLead(models.Model):
    STATUS_NEW = "new"
    STATUS_REVIEWING = "reviewing"
    STATUS_CONTACTED = "contacted"
    STATUS_SHORTLISTED = "shortlisted"
    STATUS_REJECTED = "rejected"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REVIEWING, "Reviewing"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_SHORTLISTED, "Shortlisted"),
        (STATUS_REJECTED, "Rejected"),
    ]

    ROLE_CHOICES = [
        ("sales_agent", "Sales Agent"),
        ("underwriter", "Underwriter"),
        ("merchant_admin", "Merchant Administrator"),
        ("customer_support", "Customer Support Agent"),
        ("software_engineer", "Software Engineer"),
        ("data_analyst", "Data / Credit Risk Analyst"),
        ("operations_manager", "Operations Manager"),
        ("other", "Other"),
    ]

    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    district = models.CharField(max_length=100)
    role_interested = models.CharField(max_length=30, choices=ROLE_CHOICES)
    note = models.TextField(blank=True)
    cv_file = models.FileField(upload_to="career_cvs/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    assigned_to = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="career_leads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Career Lead"
        verbose_name_plural = "Career Leads"

    def __str__(self):
        return f"{self.full_name} — {self.get_role_interested_display()}"
