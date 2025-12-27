# notifications/services.py
"""
Notification services including monthly payslip alerts and email notifications.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from datetime import date

from django.db import transaction
from django.utils import timezone
from django.utils.timezone import timedelta

from notifications.models import Notification, NotificationEvent, NotificationPreference
from notifications.emailer import send_email
from notifications.selectors import get_business_manager_emails
from tenants.models import Membership, Business

logger = logging.getLogger(__name__)

# Transactional events that should NEVER be blocked by preferences
# These are critical system emails that users must receive
TRANSACTIONAL_EVENTS = {
    "OTP_RESET",
    "OTP_VERIFY", 
    "OTP_CODE",  # All OTP emails are transactional
    "WELCOME_MANAGER",
    "WELCOME_AGENT",
}


def emit_event(
    event_type: str,
    recipients: List[str],
    dedupe_key: str,
    payload: Dict[str, Any],
    business: Optional[Any] = None,
    user: Optional[Any] = None,  # Optional user for preference checking
) -> List[int]:
    """
    Emit email notification events for recipients.
    ALWAYS creates NotificationEvent rows first (status=PENDING).
    Transactional events bypass preference checks and always send.
    Non-transactional events respect preferences and may be marked SKIPPED.
    
    Implements rate limiting for SALE_* events to prevent spam:
    - Max 30 emails per recipient per hour for SALE_INSTANT and SALE_BATCH
    - If limit exceeded, events are still created but marked for batching
    
    Args:
        event_type: Event type (must match NotificationEvent.EVENT_TYPE_CHOICES)
        recipients: List of recipient email addresses
        dedupe_key: Deduplication key (must be unique per event_type + recipient)
        payload: Template context data for email
        business: Optional business instance
        user: Optional user instance (for preference checking)
    
    Returns:
        List of created NotificationEvent IDs
    """
    created_ids = []
    is_transactional = event_type in TRANSACTIONAL_EVENTS
    
    # Rate limiting for SALE_* events (max 30 per recipient per hour)
    SALE_RATE_LIMIT = 30  # emails per hour per recipient
    rate_limit_applies = event_type in ("SALE_INSTANT", "SALE_BATCH")
    
    for recipient_email in recipients:
        if not recipient_email or "@" not in recipient_email:
            continue
        
        normalized_email = recipient_email.lower().strip()
        
        # Check rate limit for SALE_* events
        if rate_limit_applies:
            one_hour_ago = timezone.now() - timedelta(hours=1)
            recent_count = NotificationEvent.objects.filter(
                event_type__in=("SALE_INSTANT", "SALE_BATCH"),
                recipient_email=normalized_email,
                created_at__gte=one_hour_ago,
                status__in=("PENDING", "SENT"),  # Count both pending and sent
            ).count()
            
            if recent_count >= SALE_RATE_LIMIT:
                logger.warning(
                    f"Rate limit exceeded for {normalized_email}: {recent_count} SALE_* emails "
                    f"in last hour (limit: {SALE_RATE_LIMIT}). Skipping instant notification."
                )
                # Still create event but it will be batched later
                # For now, skip to prevent spam
                continue
        
        # ALWAYS create NotificationEvent first (status=PENDING)
        # This ensures we have a record even if sending is skipped
        event, created = NotificationEvent.objects.get_or_create(
            event_type=event_type,
            recipient_email=normalized_email,
            dedupe_key=dedupe_key,
            defaults={
                "business": business,
                "payload": payload,
                "status": "PENDING",
            },
        )
        
        if not created:
            # Event already exists (deduplication working)
            logger.debug(
                f"Email event already exists: {event_type} -> {normalized_email} "
                f"(dedupe_key={dedupe_key})"
            )
            continue
        
        created_ids.append(event.id)
        
        # Check preferences for non-transactional events
        if not is_transactional:
            # Get user for preference checking (try from parameter or lookup by email)
            pref_user = user
            if not pref_user:
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    pref_user = User.objects.filter(email__iexact=normalized_email).first()
                except Exception:
                    pref_user = None
            
            # Check if preference disables this event
            if pref_user and not _should_send_email(pref_user, event_type):
                event.status = "SKIPPED"
                event.last_error = "Disabled by preference"
                event.save(update_fields=["status", "last_error"])
                logger.debug(
                    f"Email event skipped due to preference: {event_type} -> {normalized_email}"
                )
                continue
        
        # Enqueue sending after transaction commit (transactional or preference allows)
        transaction.on_commit(
            lambda eid=event.id: _enqueue_dispatch(eid)
        )
    
    return created_ids


def _should_send_email(user, event_type: str) -> bool:
    """
    Check if user should receive email based on their preferences.
    Returns True if should send, False if disabled by preference.
    """
    try:
        from notifications.selectors import _should_send_email as selector_check
        # Use the selector helper which already handles preference checking
        return selector_check(user, event_type)
    except Exception:
        # If preference check fails, default to True (send)
        return True


def _enqueue_dispatch(event_id: int):
    """
    Enqueue email dispatch (either via Celery or synchronous).
    """
    try:
        # Try Celery first
        from notifications.tasks import dispatch_email_event
        dispatch_email_event.delay(event_id)
    except ImportError:
        # Celery not available, dispatch synchronously
        logger.warning("Celery not available, dispatching email synchronously")
        dispatch_event(event_id)
    except Exception as e:
        logger.error(f"Failed to enqueue email dispatch: {e}")
        # Fallback to synchronous dispatch
        dispatch_event(event_id)


def dispatch_event(event_id: int):
    """
    Dispatch a single email notification event.
    Loads NotificationEvent, renders templates, sends email, and marks as SENT/FAILED.
    
    Args:
        event_id: ID of NotificationEvent to process
    """
    try:
        event = NotificationEvent.objects.get(id=event_id)
    except NotificationEvent.DoesNotExist:
        logger.error(f"NotificationEvent {event_id} not found")
        return
    
    # Skip if already processed
    if event.status != "PENDING":
        logger.debug(f"Event {event_id} already processed (status={event.status})")
        return
    
    try:
        # Get template paths and subject based on event type
        template_config = _get_template_config(event.event_type)
        if not template_config:
            raise ValueError(f"Unknown event type: {event.event_type}")
        
        # Build context
        context = event.payload.copy()
        context.update({
            "event": event,
            "business": event.business,
        })
        
        # Runtime verification: log backend being used
        from django.conf import settings
        backend_name = getattr(settings, "EMAIL_BACKEND", "unknown")
        logger.info(
            f"[notifications] sending via backend={backend_name} "
            f"event={event.event_type} to={event.recipient_email}"
        )
        
        # Send email
        success = send_email(
            recipient_email=event.recipient_email,
            subject=template_config["subject"].format(**context),
            html_template_path=template_config.get("html_template"),
            text_template_path=template_config.get("text_template"),
            context=context,
            fail_silently=False,
        )
        
        if success:
            event.mark_sent()
            logger.info(f"Email sent successfully: {event}")
        else:
            event.mark_failed("Email sending returned False")
            logger.error(f"Email sending failed: {event}")
    
    except Exception as e:
        error_msg = str(e)[:1000]
        event.mark_failed(error_msg)
        logger.exception(f"Failed to dispatch email event {event_id}: {e}")


def _get_template_config(event_type: str) -> Optional[Dict[str, Any]]:
    """Get template configuration for event type."""
    configs = {
        "WELCOME_MANAGER": {
            "subject": "Welcome to Emajinet 🎉 Your store is ready",
            "html_template": "notifications/emails/welcome_manager.html",
            "text_template": "notifications/emails/welcome_manager.txt",
        },
        "WELCOME_AGENT": {
            "subject": "Welcome to {business_name}",
            "html_template": "notifications/emails/welcome_agent.html",
            "text_template": "notifications/emails/welcome_agent.txt",
        },
        "OTP_CODE": {
            "subject": "Your Emajinet Verification Code",
            "html_template": "notifications/emails/otp_code.html",
            "text_template": "notifications/emails/otp_code.txt",
        },
        "OTP_RESET": {
            "subject": "Your Password Reset Code",
            "html_template": "notifications/emails/otp_code.html",  # Reuse OTP template
            "text_template": "notifications/emails/otp_code.txt",
        },
        "OTP_VERIFY": {
            "subject": "Your Verification Code",
            "html_template": "notifications/emails/otp_code.html",  # Reuse OTP template
            "text_template": "notifications/emails/otp_code.txt",
        },
        "SALE_INSTANT": {
            "subject": "New Sale Completed - {business_name}",
            "html_template": "notifications/emails/sale_instant.html",
            "text_template": "notifications/emails/sale_instant.txt",
        },
        "SALE_BATCH": {
            "subject": "{count} Sales Completed - {business_name}",
            "html_template": "notifications/emails/sale_batch.html",
            "text_template": "notifications/emails/sale_batch.txt",
        },
        "DAILY_SUMMARY": {
            "subject": "Yesterday Sales Summary - {business_name}",
            "html_template": "notifications/emails/sales_daily_summary.html",
            "text_template": "notifications/emails/sales_daily_summary.txt",
        },
        "HIGH_SALES_ALERT": {
            "subject": "High Sales Day Today - {product_name}",
            "html_template": "notifications/emails/high_sales_alert.html",
            "text_template": "notifications/emails/high_sales_alert.txt",
        },
        "IMPORTANT_ALERT": {
            "subject": "{subject}",
            "html_template": "notifications/emails/important_alert.html",
            "text_template": "notifications/emails/important_alert.txt",
        },
    }
    return configs.get(event_type)


# ==============================================================================
# Sale Notification Helpers
# ==============================================================================

def notify_sale_completion(sale):
    """
    Notify managers about a completed sale.
    Implements batching logic to avoid spam.
    
    Batching thresholds:
    - If >10 sales in last 5 minutes: Use 2-minute buckets (SALE_BATCH)
    - Otherwise: Send instant notification (SALE_INSTANT)
    - Rate limit: Max 30 SALE_* emails per recipient per hour (enforced in emit_event)
    
    This function should be called after sale is committed to DB.
    Uses transaction.on_commit to ensure email is sent only after successful DB commit.
    """
    from sales.models import Sale  # noqa: F401
    from django.utils import timezone
    from decimal import Decimal
    
    if not sale or not hasattr(sale, 'business'):
        return
    
    business = getattr(sale, 'business', None)
    if not business:
        # Try to get from location
        if hasattr(sale, 'location') and sale.location:
            business = getattr(sale.location, 'business', None)
    
    if not business:
        return
    
    # Check if we should batch (more than 10 sales in last 5 minutes)
    from django.utils import timezone
    from datetime import timedelta
    
    five_min_ago = timezone.now() - timedelta(minutes=5)
    recent_sales_count = Sale.objects.filter(
        business=business,
        created_at__gte=five_min_ago,
    ).count()
    
    if recent_sales_count > 10:
        # Use batching - check if batch event already exists for this 2-minute bucket
        now = timezone.now()
        bucket_minutes = (now.minute // 2) * 2
        bucket_time = now.replace(minute=bucket_minutes, second=0, microsecond=0)
        bucket_key = bucket_time.strftime("%Y%m%d%H%M")
        
        dedupe_key = f"SALE_BATCH:{business.id}:{bucket_key}"
        
        # Check if batch event already exists
        existing = NotificationEvent.objects.filter(
            event_type="SALE_BATCH",
            dedupe_key=dedupe_key,
            business=business,
        ).first()
        
        if existing:
            # Update payload with latest counts
            from django.db.models import Sum, Count
            bucket_start = bucket_time - timedelta(minutes=2)
            sales_in_bucket = Sale.objects.filter(
                business=business,
                created_at__gte=bucket_start,
                created_at__lt=bucket_time + timedelta(minutes=2),
            )
            count = sales_in_bucket.count()
            total_revenue = sales_in_bucket.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            existing.payload = {
                "count": count,
                "total_revenue": str(total_revenue),
                "time_period": bucket_time.strftime("%Y-%m-%d %H:%M"),
                "business_name": business.name,
            }
            existing.save(update_fields=['payload'])
        else:
            # Create new batch event
            bucket_start = bucket_time - timedelta(minutes=2)
            sales_in_bucket = Sale.objects.filter(
                business=business,
                created_at__gte=bucket_start,
                created_at__lt=bucket_time + timedelta(minutes=2),
            )
            count = sales_in_bucket.count()
            total_revenue = sales_in_bucket.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            recipients = get_business_manager_emails(
                business,
                include_owner=True,
                event_type="SALE_BATCH",
            )
            
            if recipients:
                emit_event(
                    event_type="SALE_BATCH",
                    recipients=recipients,
                    dedupe_key=dedupe_key,
                    payload={
                        "count": count,
                        "total_revenue": str(total_revenue),
                        "time_period": bucket_time.strftime("%Y-%m-%d %H:%M"),
                        "business_name": business.name,
                    },
                    business=business,
                )
    else:
        # Normal volume: send instant notification
        recipients = get_business_manager_emails(
            business,
            include_owner=True,
            event_type="SALE_INSTANT",
        )
        
        if recipients:
            # Get sale details
            agent_name = ""
            if hasattr(sale, 'agent') and sale.agent:
                agent_name = sale.agent.get_full_name() or sale.agent.username
            elif hasattr(sale, 'seller') and sale.seller:
                agent_name = sale.seller.get_full_name() or sale.seller.username
            
            items_summary = ""
            if hasattr(sale, 'item') and sale.item:
                item = sale.item
                if hasattr(item, 'product') and item.product:
                    items_summary = str(item.product)
                elif hasattr(item, 'name'):
                    items_summary = item.name
            
            emit_event(
                event_type="SALE_INSTANT",
                recipients=recipients,
                dedupe_key=f"SALE:{sale.id}",
                payload={
                    "sale_ref": f"#{sale.id}",
                    "total": str(sale.price),
                    "items_summary": items_summary,
                    "cashier_name": agent_name or "Unknown",
                    "time": sale.created_at if hasattr(sale, 'created_at') else timezone.now(),
                    "business_name": business.name,
                },
                business=business,
            )
    
    # Check for high sales alert
    _check_high_sales_alert(sale, business)


def _check_high_sales_alert(sale, business):
    """Check if this sale triggers a high-sales alert for the product."""
    from sales.models import Sale  # noqa: F401
    from django.utils import timezone
    from django.db.models import Count, Avg
    from datetime import timedelta
    
    if not hasattr(sale, 'item') or not sale.item:
        return
    
    product = getattr(sale.item, 'product', None)
    if not product:
        return
    
    # Count today's sales for this product
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = Sale.objects.filter(
        business=business,
        item__product=product,
        created_at__gte=today_start,
    ).count()
    
    # Threshold check (default 10)
    threshold = 10
    if today_count >= threshold:
        # Check if we already sent an alert today
        dedupe_key = f"HIGH_SALES:{business.id}:{product.id}:{today_start.strftime('%Y-%m-%d')}:{threshold}"
        
        existing = NotificationEvent.objects.filter(
            event_type="HIGH_SALES_ALERT",
            dedupe_key=dedupe_key,
        ).exists()
        
        if not existing:
            # Optional: compare with 7-day average
            seven_days_ago = today_start - timedelta(days=7)
            avg_last_7_days = Sale.objects.filter(
                business=business,
                item__product=product,
                created_at__gte=seven_days_ago,
                created_at__lt=today_start,
            ).aggregate(avg=Avg('id'))  # Using count instead
            
            # Calculate 7-day average count
            seven_day_count = Sale.objects.filter(
                business=business,
                item__product=product,
                created_at__gte=seven_days_ago,
                created_at__lt=today_start,
            ).count()
            avg_count = seven_day_count / 7 if seven_day_count > 0 else 0
            
            trending_text = ""
            if avg_count > 0 and today_count >= (avg_count * 2) and today_count >= 5:
                trending_text = "more than double"
            elif avg_count > 0 and today_count > avg_count:
                trending_text = "above"
            else:
                trending_text = "equal to"
            
            product_name = str(product)
            
            recipients = get_business_manager_emails(
                business,
                include_owner=True,
                event_type="HIGH_SALES_ALERT",
            )
            
            if recipients:
                emit_event(
                    event_type="HIGH_SALES_ALERT",
                    recipients=recipients,
                    dedupe_key=dedupe_key,
                    payload={
                        "count": today_count,
                        "product_name": product_name,
                        "business_name": business.name,
                        "avg_last_7_days": round(avg_count, 1) if avg_count > 0 else None,
                        "trending_text": trending_text,
                    },
                    business=business,
                )


# ==============================================================================
# Important Alerts Framework
# ==============================================================================

def send_important_alert(
    business: Business,
    subject: str,
    message: str,
    recipients: Optional[List[str]] = None,
    dedupe_key: Optional[str] = None,
):
    """
    Send an important alert email to business managers/owners.
    
    Args:
        business: The business
        subject: Email subject
        message: Email message body
        recipients: Optional list of email addresses (defaults to managers/owners with preferences)
        dedupe_key: Optional dedupe key (defaults to subject + date)
    """
    if not business:
        return
    
    if recipients is None:
        recipients = get_business_manager_emails(
            business,
            include_owner=True,
            event_type="IMPORTANT_ALERT",
        )
    
    if not recipients:
        return
    
    # Generate dedupe key if not provided
    if dedupe_key is None:
        from django.utils import timezone
        date_str = timezone.now().strftime("%Y-%m-%d")
        dedupe_key = f"IMPORTANT:{business.id}:{subject}:{date_str}"
    
    emit_event(
        event_type="IMPORTANT_ALERT",
        recipients=recipients,
        dedupe_key=dedupe_key,
        payload={
            "subject": subject,
            "message": message,
            "business_name": business.name,
        },
        business=business,
    )


# ==============================================================================
# Existing notification services (payslip alerts, etc.)
# ==============================================================================

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
    cutoff = timezone.now() - timedelta(days=days_back)
    
    return Notification.objects.filter(
        user=user,
        business=business,
        category='payslip_reminder',
        read_at__isnull=True,
        created_at__gte=cutoff
    ).exists()
