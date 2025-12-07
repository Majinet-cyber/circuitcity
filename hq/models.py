"""
HQ app models for tracking gamification metrics and merchant contracts.
"""
from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model
from tenants.models import Business

User = get_user_model()


class AgentMilestone(models.Model):
    """
    Track agent milestones for gamification.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='milestones')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='agent_milestones')
    
    milestone_type = models.CharField(max_length=50)  # e.g., "sales_10", "sales_25", etc.
    milestone_name = models.CharField(max_length=100)  # e.g., "Rising Star"
    milestone_emoji = models.CharField(max_length=10, default="⭐")
    
    sales_count = models.IntegerField(default=0)  # The sales count when milestone was achieved
    achieved_at = models.DateTimeField(auto_now_add=True)
    
    # Period tracking (optional - to track per month)
    year = models.IntegerField(null=True, blank=True)
    month = models.IntegerField(null=True, blank=True)
    
    class Meta:
        unique_together = ('user', 'business', 'milestone_type', 'year', 'month')
        ordering = ['-achieved_at']
        indexes = [
            models.Index(fields=['user', 'business']),
            models.Index(fields=['business', 'year', 'month']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.milestone_name} ({self.sales_count} sales)"


class MerchantContract(models.Model):
    """
    Stores signed merchant contracts for businesses (HQ-managed).
    """
    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name="merchant_contract",
        help_text="The business this contract is for"
    )
    file = models.FileField(
        upload_to="contracts/",
        help_text="Signed contract PDF file"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_contracts",
        help_text="HQ staff member who uploaded this contract"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(
        blank=True,
        help_text="Internal notes about this contract"
    )
    
    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['business']),
            models.Index(fields=['uploaded_at']),
        ]
    
    def __str__(self):
        return f"Contract for {self.business.name}"
    
    @property
    def is_signed(self):
        """Returns True if a contract file exists"""
        return bool(self.file)
