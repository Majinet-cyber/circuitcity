# notifications/services.py
"""
Notification services including monthly payslip alerts.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from tenants.models import Membership, Business


def create_monthly_payslip_alerts(today: Optional[date] = None) -> int:
    """
    Create monthly payslip reminder notifications on the 27th of each month.
    
    Creates ONE notification per active user per business per month to remind
    agents and managers that payslip day is coming and salaries close soon.
    
    Args:
        today: Override the current date (for testing). Defaults to today.
    
    Returns:
        Number of notifications created.
    
    Usage:
        # In a daily cron job or Celery Beat task:
        from notifications.services import create_monthly_payslip_alerts
        create_monthly_payslip_alerts()
    """
    today = today or timezone.localdate()
    
    # Only run on the 27th of each month
    if today.day != 27:
        return 0
    
    created_count = 0
    year = today.year
    month = today.month
    
    # Get all active businesses
    businesses = Business.objects.filter(status='ACTIVE')
    
    for business in businesses:
        # Get all active memberships (agents + managers) for this business
        memberships = Membership.objects.filter(
            business=business,
            status='ACTIVE'
        ).select_related('user').distinct()
        
        for membership in memberships:
            user = membership.user
            
            # Check if notification already exists for this user/business/month
            # to ensure idempotency
            existing = Notification.objects.filter(
                user=user,
                business=business,
                category='payslip_reminder',
                created_at__year=year,
                created_at__month=month
            ).exists()
            
            if existing:
                continue  # Skip if already notified this month
            
            # Create the payslip reminder notification
            with transaction.atomic():
                Notification.objects.create(
                    user=user,
                    business=business,
                    audience='AGENT' if membership.role == 'AGENT' else 'ADMIN',
                    category='payslip_reminder',
                    level='info',
                    message='Payslip day is coming – salaries close soon. Please check your wallet and sales.',
                    meta={
                        'year': year,
                        'month': month,
                        'membership_id': membership.id,
                        'role': membership.role,
                    }
                )
                created_count += 1
    
    return created_count


def mark_notification_read(notification_id: int, user) -> bool:
    """
    Mark a notification as read.
    
    Args:
        notification_id: ID of the notification
        user: User marking it as read (must be the owner)
    
    Returns:
        True if marked successfully, False otherwise
    """
    try:
        notification = Notification.objects.get(id=notification_id, user=user)
        notification.mark_read()
        return True
    except Notification.DoesNotExist:
        return False


def get_unread_count(user, business: Optional[Business] = None) -> int:
    """
    Get count of unread notifications for a user.
    
    Args:
        user: The user
        business: Optional business filter
    
    Returns:
        Count of unread notifications
    """
    qs = Notification.objects.filter(user=user, read_at__isnull=True)
    
    if business:
        qs = qs.filter(business=business)
    
    return qs.count()


def get_recent_notifications(user, business: Optional[Business] = None, limit: int = 10):
    """
    Get recent notifications for a user.
    
    Args:
        user: The user
        business: Optional business filter
        limit: Maximum number to return
    
    Returns:
        QuerySet of recent notifications
    """
    qs = Notification.objects.filter(user=user)
    
    if business:
        qs = qs.filter(business=business)
    
    return qs.order_by('-created_at')[:limit]


def has_unread_payslip_alert(user, business: Business, days_back: int = 7) -> bool:
    """
    Check if user has an unread payslip reminder within the last X days.
    
    Args:
        user: The user
        business: The business
        days_back: How many days to look back (default: 7)
    
    Returns:
        True if there's an unread payslip reminder
    """
    cutoff = timezone.now() - timezone.timedelta(days=days_back)
    
    return Notification.objects.filter(
        user=user,
        business=business,
        category='payslip_reminder',
        read_at__isnull=True,
        created_at__gte=cutoff
    ).exists()

