"""
HQ app models for tracking gamification metrics.
"""
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
