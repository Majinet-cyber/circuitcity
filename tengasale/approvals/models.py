from django.conf import settings
from django.db import models

from applications.models import FinancingApplication


class UnderwriterReview(models.Model):
    application = models.OneToOneField(
        FinancingApplication,
        on_delete=models.CASCADE,
        related_name="underwriter_review",
    )
    underwriter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    summary_clear = models.BooleanField(null=True, blank=True)

    identity_signature_matches = models.BooleanField(null=True, blank=True)
    identity_info_matches = models.BooleanField(null=True, blank=True)

    momo_name_matches = models.BooleanField(null=True, blank=True)

    customer_spoken = models.BooleanField(null=True, blank=True)
    customer_intro_done = models.BooleanField(null=True, blank=True)
    customer_confirmed_application = models.BooleanField(null=True, blank=True)
    customer_confirmed_device = models.BooleanField(null=True, blank=True)
    customer_confirmed_deposit = models.BooleanField(null=True, blank=True)
    customer_confirmed_repayment = models.BooleanField(null=True, blank=True)
    customer_understands_direct_payment = models.BooleanField(null=True, blank=True)
    customer_understands_nonpayment = models.BooleanField(null=True, blank=True)

    income_understood = models.BooleanField(null=True, blank=True)
    income_contact_spoken = models.BooleanField(null=True, blank=True)
    income_confirmed = models.BooleanField(null=True, blank=True)
    income_source_dependable = models.BooleanField(null=True, blank=True)
    income_contact_confident = models.BooleanField(null=True, blank=True)

    location_neighbour_spoken = models.BooleanField(null=True, blank=True)
    location_confirmed = models.BooleanField(null=True, blank=True)
    location_traceable = models.BooleanField(null=True, blank=True)

    comment = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = [
        "summary_clear",
        "identity_signature_matches",
        "identity_info_matches",
        "momo_name_matches",
        "customer_spoken",
        "customer_intro_done",
        "customer_confirmed_application",
        "customer_confirmed_device",
        "customer_confirmed_deposit",
        "customer_confirmed_repayment",
        "customer_understands_direct_payment",
        "customer_understands_nonpayment",
        "income_understood",
        "income_contact_spoken",
        "income_confirmed",
        "income_source_dependable",
        "income_contact_confident",
        "location_neighbour_spoken",
        "location_confirmed",
        "location_traceable",
    ]

    def completeness_score(self):
        total = len(self.REQUIRED_FIELDS)
        answered = sum(1 for field in self.REQUIRED_FIELDS if getattr(self, field) is not None)
        return round((answered / total) * 100) if total else 0

    def __str__(self):
        return f"Review for {self.application}"
