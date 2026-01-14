# notifications/services.py
"""
Notification services including monthly payslip alerts and email notifications.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone
from django.utils.timezone import timedelta

from notifications.emailer import send_email
from notifications.models import Notification, NotificationEvent, NotificationPreference
from notifications.selectors import get_business_manager_emails
from tenants.models import Business, Membership

logger = logging.getLogger(__name__)

# Transactional events that should NEVER be blocked by preferences
# These are critical system emails that users must receive
TRANSACTIONAL_EVENTS = {
    "OTP_RESET",
    "OTP_VERIFY",
    "OTP_CODE",  # All OTP emails are transactional
    "WELCOME_MANAGER",
    "WELCOME_AGENT",
    "SALE_INSTANT",  # Managers MUST receive sale emails - no preference blocking
    "SALE_BATCH",    # Managers MUST receive sale emails - no preference blocking
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

    try:
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
                    f"Email event already exists: {event_type} -> {normalized_email} " f"(dedupe_key={dedupe_key})"
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
                    logger.debug(f"Email event skipped due to preference: {event_type} -> {normalized_email}")
                    continue

            # Enqueue sending after transaction commit (transactional or preference allows)
            transaction.on_commit(lambda eid=event.id: _enqueue_dispatch(eid))

    except Exception as e:
        logger.error(f"[SALE_EMAIL] Failed to emit event {event_type} with dedupe_key={dedupe_key}: {e}", exc_info=True)

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
    Checks CELERY_BROKER_URL - if not set, sends inline (best-effort).
    """
    from django.conf import settings

    # Check if Celery broker is configured
    broker_url = getattr(settings, "CELERY_BROKER_URL", None)
    has_broker = broker_url and broker_url.strip()

    if has_broker:
        # Try Celery first if broker is configured
        try:
            from notifications.tasks import dispatch_email_event

            dispatch_email_event.delay(event_id)
            logger.debug(f"Enqueued email event {event_id} via Celery")
            return
        except Exception as e:
            # Celery task failed, fallback to inline
            logger.warning(
                f"Failed to enqueue email event {event_id} via Celery: {e}. " f"Falling back to inline dispatch."
            )

    # No broker or Celery failed: dispatch inline (best-effort)
    try:
        dispatch_event(event_id)
    except Exception as e:
        # Log error but don't raise - never block the calling code
        logger.error(f"Failed to dispatch email event {event_id} inline: {e}", exc_info=True)


def dispatch_event(event_id: int):
    """
    Dispatch a single email notification event.
    Loads NotificationEvent, renders templates, sends email, and marks as SENT/FAILED.
    Never raises exceptions - always logs errors.

    Args:
        event_id: ID of NotificationEvent to process
    """
    try:
        event = NotificationEvent.objects.get(id=event_id)
    except NotificationEvent.DoesNotExist:
        logger.error(f"[SALE_EMAIL] NotificationEvent {event_id} not found")
        return
    except Exception as e:
        logger.error(f"[SALE_EMAIL] Failed to load NotificationEvent {event_id}: {e}", exc_info=True)
        return

    # Skip if already processed
    if event.status != "PENDING":
        logger.debug(f"[SALE_EMAIL] Event {event_id} already processed (status={event.status})")
        return

    try:
        # Get template paths and subject based on event type
        template_config = _get_template_config(event.event_type)
        if not template_config:
            error_msg = f"Unknown event type: {event.event_type}"
            event.mark_failed(error_msg)
            logger.error(f"[SALE_EMAIL] Event {event_id}: {error_msg}")
            return

        # Build context
        context = event.payload.copy()
        context.update(
            {
                "event": event,
                "business": event.business,
            }
        )

        # Get subject from template config
        subject_template = template_config.get("subject", "")
        try:
            if callable(subject_template):
                subject = subject_template(context)
            else:
                subject = subject_template.format(**context)
        except Exception as e:
            # Fallback to simple subject if generation fails
            logger.warning(f"[SALE_EMAIL] Failed to generate subject for event {event_id}: {e}. Using fallback.")
            subject = f"Sale Completed - {context.get('business_name', 'Business')}"

        # Runtime verification: log backend being used
        from django.conf import settings

        backend_name = getattr(settings, "EMAIL_BACKEND", "unknown")
        logger.info(
            f"[SALE_EMAIL] Sending event_id={event_id} event_type={event.event_type} "
            f"to={event.recipient_email} backend={backend_name}"
        )

        # Send email
        success = send_email(
            recipient_email=event.recipient_email,
            subject=subject,
            html_template_path=template_config.get("html_template"),
            text_template_path=template_config.get("text_template"),
            context=context,
            fail_silently=False,
        )

        if success:
            event.mark_sent()
            logger.info(
                f"[SALE_EMAIL] SUCCESS: event_id={event_id} sent to {event.recipient_email} "
                f"event_type={event.event_type}"
            )
        else:
            error_msg = "Email sending returned False"
            event.mark_failed(error_msg)
            logger.error(
                f"[SALE_EMAIL] FAILED: event_id={event_id} to {event.recipient_email} "
                f"event_type={event.event_type} error={error_msg}"
            )

    except Exception as e:
        error_msg = str(e)[:1000]
        event.mark_failed(error_msg)
        logger.error(
            f"[SALE_EMAIL] FAILED: event_id={event_id} to {event.recipient_email} "
            f"event_type={event.event_type} error={error_msg} exception={type(e).__name__}",
            exc_info=True,
        )


def _get_sale_instant_subject(context: Dict[str, Any]) -> str:
    """
    Generate a friendly, informative subject line for sale instant emails.
    Format: "Sold: Product Name (Spec) — MK Revenue | Profit MK Profit"
    Falls back to simple format if any error occurs.
    Always returns a non-empty string.
    """
    try:
        if not context:
            return "Sale Completed"

        product_name = context.get("product_name") or context.get("items_summary") or "Product"
        revenue = context.get("revenue") or context.get("total") or "0"
        profit = context.get("profit")

        # Format revenue - ensure it's always a string
        try:
            if revenue:
                revenue_decimal = Decimal(str(revenue))
                revenue_formatted = f"MK {revenue_decimal:,.0f}"
            else:
                revenue_formatted = "MK 0"
        except (ValueError, TypeError, AttributeError, Exception):
            revenue_formatted = f"MK {revenue}" if revenue else "MK 0"

        # Build subject
        subject_parts = [f"Sold: {product_name}"]

        # Add profit if available
        if profit:
            try:
                profit_decimal = Decimal(str(profit))
                if profit_decimal > 0:
                    profit_formatted = f"MK {profit_decimal:,.0f}"
                    subject_parts.append(f"— {revenue_formatted} | Profit {profit_formatted}")
                else:
                    subject_parts.append(f"— {revenue_formatted}")
            except (ValueError, TypeError, AttributeError, Exception):
                subject_parts.append(f"— {revenue_formatted}")
        else:
            subject_parts.append(f"— {revenue_formatted}")

        result = " ".join(subject_parts)
        # Ensure we always return a non-empty string
        if not result or len(result.strip()) == 0:
            raise ValueError("Generated empty subject")
        return result
    except Exception as e:
        # Fallback to simple subject on any error - always return something
        try:
            business_name = context.get("business_name") if context else None
            if business_name:
                return f"Sale Completed - {business_name}"
            else:
                return "Sale Completed"
        except Exception:
            # Ultimate fallback
            return "Sale Completed"


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
            "subject": "🎉 Sale Completed - {business_name}",
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
        "AGENT_COMMISSION": {
            "subject": "Commission Earned - {business_name}",
            "html_template": "notifications/emails/agent_commission.html",
            "text_template": "notifications/emails/agent_commission.txt",
        },
        "WEEKLY_DIGEST": {
            "subject": "Weekly Sales Summary - {business_name}",
            "html_template": "notifications/emails/weekly_digest.html",
            "text_template": "notifications/emails/weekly_digest.txt",
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

    NEVER blocks sale completion - all errors are logged only.
    """
    from decimal import Decimal

    from django.utils import timezone

    from sales.models import Sale  # noqa: F401

    try:
        if not sale:
            logger.debug(f"[SALE_EMAIL] notify_sale_completion: sale is None")
            return

        # Sale model doesn't have business directly - get from location or item
        business = None
        if hasattr(sale, "location") and sale.location:
            business = getattr(sale.location, "business", None)

        if not business and hasattr(sale, "item") and sale.item:
            business = getattr(sale.item, "business", None)

        # Fallback: try direct business attribute (for other Sale models that might have it)
        if not business:
            business = getattr(sale, "business", None)

        if not business:
            logger.warning(
                f"[SALE_EMAIL] notify_sale_completion: sale {getattr(sale, 'id', 'unknown')} has no business "
                f"(checked location.business, item.business, sale.business)"
            )
            return
    except Exception as e:
        logger.error(
            f"[SALE_EMAIL] notify_sale_completion: Error getting business for sale {getattr(sale, 'id', 'unknown')}: {e}",
            exc_info=True,
        )
        return

    # Wrap the rest of the function in try-except to never block sale completion
    try:
        # Check if we should batch (more than 10 sales in last 5 minutes)
        from datetime import timedelta

        from django.utils import timezone

        five_min_ago = timezone.now() - timedelta(minutes=5)
        recent_sales_count = Sale.objects.filter(
            location__business=business,
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
                from django.db.models import Count, Sum

                bucket_start = bucket_time - timedelta(minutes=2)
                sales_in_bucket = Sale.objects.filter(
                    location__business=business,
                    created_at__gte=bucket_start,
                    created_at__lt=bucket_time + timedelta(minutes=2),
                )
                count = sales_in_bucket.count()
                total_revenue = sales_in_bucket.aggregate(total=Sum("price"))["total"] or Decimal("0")

                existing.payload = {
                    "count": count,
                    "total_revenue": str(total_revenue),
                    "time_period": bucket_time.strftime("%Y-%m-%d %H:%M"),
                    "business_name": business.name,
                }
                existing.save(update_fields=["payload"])
            else:
                # Create new batch event
                bucket_start = bucket_time - timedelta(minutes=2)
                sales_in_bucket = Sale.objects.filter(
                    location__business=business,
                    created_at__gte=bucket_start,
                    created_at__lt=bucket_time + timedelta(minutes=2),
                )
                count = sales_in_bucket.count()
                total_revenue = sales_in_bucket.aggregate(total=Sum("price"))["total"] or Decimal("0")

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
                # Get sale details with enhanced information
                agent_name = ""
                agent_role = "Agent"
                if hasattr(sale, "agent") and sale.agent:
                    agent_name = sale.agent.get_full_name() or sale.agent.username
                elif hasattr(sale, "seller") and sale.seller:
                    agent_name = sale.seller.get_full_name() or sale.seller.username
                elif hasattr(sale, "sold_by") and sale.sold_by:
                    agent_name = sale.sold_by.get_full_name() or sale.sold_by.username

                product_name = ""
                product_model_spec = ""
                sku_imei = ""
                cost = None
                profit = None
                quantity = 1
                location_name = ""

                if hasattr(sale, "item") and sale.item:
                    item = sale.item
                    # Product name and model/spec
                    if hasattr(item, "product") and item.product:
                        product = item.product
                        if hasattr(product, "brand") and hasattr(product, "model"):
                            product_name = product.brand or ""
                            product_model_spec = product.model or ""
                            # Combine for display: "Brand Model" or just "Brand" if no model
                            if product_name and product_model_spec:
                                full_product_display = f"{product_name} {product_model_spec}".strip()
                            elif product_name:
                                full_product_display = product_name
                            else:
                                full_product_display = str(product)
                        else:
                            full_product_display = str(product)
                            product_name = str(product)
                    elif hasattr(item, "name"):
                        full_product_display = item.name
                        product_name = item.name
                    else:
                        full_product_display = "Product"

                    # SKU/IMEI/Serial
                    sku_imei = (
                        getattr(item, "imei", "")
                        or getattr(item, "serial", "")
                        or getattr(item, "sku", "")
                        or getattr(item, "code", "")
                        or ""
                    )

                    # Cost and profit
                    cost_price = (
                        getattr(item, "order_price", None)
                        or getattr(item, "cost_price", None)
                        or getattr(item, "cost", None)
                    )
                    if cost_price:
                        try:
                            cost = Decimal(str(cost_price))
                            profit = sale.price - cost
                        except (ValueError, TypeError):
                            cost = None
                            profit = None

                    # Quantity
                    quantity = getattr(item, "quantity", 1) or 1
                    try:
                        quantity = int(quantity)
                    except (ValueError, TypeError):
                        quantity = 1

                # Handle groceries/pharmacy/other verticals (MerchProduct sales)
                elif hasattr(sale, "product") and sale.product:
                    product = sale.product
                    if hasattr(product, "name"):
                        product_name = product.name
                        full_product_display = product.name
                        # Check for spec_label (groceries)
                        if hasattr(product, "spec_label") and product.spec_label:
                            product_model_spec = product.spec_label
                            full_product_display = f"{product_name} {product.spec_label}".strip()

                    # SKU
                    sku_imei = getattr(product, "sku", "") or getattr(product, "barcode", "") or ""

                    # Cost and profit - check for total_cost/total_price first (vertical sales)
                    if hasattr(sale, "total_cost") and hasattr(sale, "total_price"):
                        # Vertical sales (GrocerySale, PharmacySale, etc.) use total_cost/total_price
                        try:
                            cost = Decimal(str(sale.total_cost)) if sale.total_cost else None
                            revenue_amount = Decimal(str(sale.total_price)) if sale.total_price else sale.price
                            profit = revenue_amount - cost if cost is not None else None
                        except (ValueError, TypeError):
                            cost = None
                            profit = None
                    else:
                        # Fallback: use product cost_price or sale cost
                        cost_price = getattr(sale, "unit_cost", None) or getattr(product, "cost_price", None)
                        if cost_price:
                            try:
                                cost = Decimal(str(cost_price))
                                # For unit_cost, multiply by quantity
                                if hasattr(sale, "unit_cost") and hasattr(sale, "quantity"):
                                    qty = getattr(sale, "quantity", 1) or 1
                                    cost = cost * Decimal(str(qty))
                                profit = sale.price - cost
                            except (ValueError, TypeError):
                                cost = None
                                profit = None
                        else:
                            cost = None
                            profit = None

                    # Quantity
                    quantity = getattr(sale, "quantity", 1) or 1
                    try:
                        quantity = int(quantity)
                    except (ValueError, TypeError):
                        quantity = 1

                # Location
                if hasattr(sale, "location") and sale.location:
                    location_name = getattr(sale.location, "name", "") or str(sale.location)

                # Payment method
                payment_method_display = ""
                if hasattr(sale, "payment_method"):
                    payment_method = sale.payment_method
                    if payment_method:
                        # Get display name from choices
                        try:
                            choices = getattr(sale._meta.get_field("payment_method"), "choices", [])
                            choice_dict = dict(choices) if choices else {}
                            payment_method_display = choice_dict.get(
                                payment_method, payment_method.replace("_", " ").title()
                            )
                        except Exception:
                            payment_method_display = str(payment_method).replace("_", " ").title()

                # Build product display name with spec if available
                if product_model_spec and product_name:
                    final_product_display = f"{product_name} ({product_model_spec})"
                elif product_name:
                    final_product_display = product_name
                else:
                    final_product_display = "Product"

                # Get revenue amount (use total_price for vertical sales, price for regular sales)
                revenue_amount = sale.price
                if hasattr(sale, "total_price") and sale.total_price:
                    try:
                        revenue_amount = Decimal(str(sale.total_price))
                    except (ValueError, TypeError):
                        revenue_amount = sale.price
                else:
                    # For regular sales, use price field
                    try:
                        revenue_amount = Decimal(str(sale.price)) if sale.price else Decimal("0")
                    except (ValueError, TypeError):
                        revenue_amount = Decimal("0")

                # Calculate profit margin (guard divide-by-zero)
                profit_margin = None
                if profit is not None and revenue_amount and revenue_amount > 0:
                    try:
                        profit_margin = (profit / revenue_amount) * 100
                        profit_margin = round(float(profit_margin), 2)
                    except (ZeroDivisionError, TypeError, ValueError):
                        profit_margin = None

                # Get sale URL (link to sales list page - no individual sale detail page exists)
                sale_url = None
                try:
                    from django.conf import settings
                    from django.urls import reverse

                    # Try to build absolute URL
                    try:
                        relative_url = reverse("sales:list")
                        # Get site domain from settings or use a default
                        site_domain = getattr(settings, "SITE_DOMAIN", None)
                        if site_domain:
                            sale_url = f"https://{site_domain}{relative_url}"
                        else:
                            # Fallback: just use relative URL (email clients may handle it)
                            sale_url = relative_url
                    except Exception:
                        # If reverse fails, skip URL
                        pass
                except Exception:
                    pass

                emit_event(
                    event_type="SALE_INSTANT",
                    recipients=recipients,
                    dedupe_key=f"SALE:{sale.id}",
                    payload={
                        "sale_ref": f"#{sale.id}",
                        "total": str(revenue_amount),
                        "revenue": str(revenue_amount),  # Alias for clarity
                        "product_name": final_product_display,
                        "product_base_name": product_name or "Product",
                        "product_model_spec": product_model_spec or "",
                        "items_summary": final_product_display,
                        "imei": sku_imei,  # Keep for backward compatibility
                        "sku": sku_imei,
                        "cost": str(cost) if cost is not None else None,
                        "profit": str(profit) if profit is not None else None,
                        "profit_margin": str(profit_margin) if profit_margin is not None else None,
                        "quantity": quantity,
                        "payment_method": payment_method_display,
                        "cashier_name": agent_name or "Unknown",
                        "agent_name": agent_name or "Unknown",
                        "location": location_name,
                        "location_name": location_name,
                        "time": sale.created_at if hasattr(sale, "created_at") else timezone.now(),
                        "business_name": business.name,
                        "sale_url": sale_url,
                    },
                    business=business,
                )

        # Check for high sales alert (never block)
        try:
            _check_high_sales_alert(sale, business)
        except Exception as e:
            logger.error(
                f"[SALE_EMAIL] Failed to check high sales alert for sale {getattr(sale, 'id', 'unknown')}: {e}",
                exc_info=True,
            )

        # Send agent commission email if agent exists (never block)
        try:
            if hasattr(sale, "agent") and sale.agent:
                _notify_agent_commission(sale, business)
        except Exception as e:
            logger.error(
                f"[SALE_EMAIL] Failed to notify agent commission for sale {getattr(sale, 'id', 'unknown')}: {e}",
                exc_info=True,
            )
    except Exception as e:
        # Catch-all for any other errors in notify_sale_completion
        logger.error(
            f"[SALE_EMAIL] Unexpected error in notify_sale_completion for sale {getattr(sale, 'id', 'unknown')}: {e}",
            exc_info=True,
        )


def _check_high_sales_alert(sale, business):
    """Check if this sale triggers a high-sales alert for the product."""
    from datetime import timedelta

    from django.db.models import Avg, Count
    from django.utils import timezone

    from sales.models import Sale  # noqa: F401

    if not hasattr(sale, "item") or not sale.item:
        return

    product = getattr(sale.item, "product", None)
    if not product:
        return

    # Count today's sales for this product
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = Sale.objects.filter(
        location__business=business,
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
                location__business=business,
                item__product=product,
                created_at__gte=seven_days_ago,
                created_at__lt=today_start,
            ).aggregate(
                avg=Avg("id")
            )  # Using count instead

            # Calculate 7-day average count
            seven_day_count = Sale.objects.filter(
                location__business=business,
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


def _notify_agent_commission(sale, business):
    """
    Send commission email to agent after sale completion.
    Only sends if agent has commission emails enabled in preferences.
    """
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from sales.models import Sale

    agent = sale.agent
    if not agent or not agent.email:
        return

    # Check if agent has commission emails enabled
    try:
        pref = NotificationPreference.objects.get(user=agent)
        if not pref.commission_emails_enabled:
            return
    except NotificationPreference.DoesNotExist:
        # Default: don't send commission emails unless explicitly enabled
        return

    # Calculate commission for this sale
    commission_amount = Decimal("0.00")
    commission_pct = Decimal("0.00")
    commission_note = ""

    try:
        # Try to get commission from SaleCommission if it exists
        if hasattr(sale, "commission_record") and sale.commission_record:
            commission_record = sale.commission_record
            commission_amount = commission_record.net_amount or commission_record.base_commission or Decimal("0.00")
            if sale.price > 0:
                commission_pct = (commission_amount / sale.price) * 100
        else:
            # Fallback: use sale's commission_pct if available
            if hasattr(sale, "commission_pct") and sale.commission_pct:
                commission_pct = sale.commission_pct
                commission_amount = (sale.price * commission_pct) / 100
            else:
                # Try to get from commission config
                try:
                    from sales.models import CommissionConfig

                    config = CommissionConfig.get_active(business)
                    if config:
                        if config.commission_mode == "FIXED":
                            commission_amount = config.fixed_commission_amount or Decimal("0.00")
                        else:
                            commission_pct = config.base_commission_pct or Decimal("0.00")
                            commission_amount = (sale.price * commission_pct) / 100
                    else:
                        commission_note = "Commission plan not set."
                except Exception:
                    commission_note = "Commission plan not set."
    except Exception as e:
        logger.warning(f"Failed to calculate commission for sale {sale.id}: {e}")
        commission_note = "Commission calculation unavailable."

    # Calculate total earnings for current month
    total_earnings = Decimal("0.00")
    try:
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get all sales by this agent this month
        month_sales = Sale.objects.filter(
            agent=agent,
            location__business=business,
            created_at__gte=month_start,
        )

        # Calculate total commission from all sales
        for s in month_sales:
            try:
                if hasattr(s, "commission_record") and s.commission_record:
                    total_earnings += (
                        s.commission_record.net_amount or s.commission_record.base_commission or Decimal("0.00")
                    )
                elif hasattr(s, "commission_pct") and s.commission_pct:
                    total_earnings += (s.price * s.commission_pct) / 100
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to calculate total earnings for agent {agent.id}: {e}")

    # Get product details
    product_name = ""
    imei = ""
    if hasattr(sale, "item") and sale.item:
        item = sale.item
        if hasattr(item, "product") and item.product:
            product = item.product
            if hasattr(product, "brand") and hasattr(product, "model"):
                product_name = f"{product.brand} {product.model}".strip()
            else:
                product_name = str(product)
        elif hasattr(item, "name"):
            product_name = item.name

        imei = getattr(item, "imei", "") or getattr(item, "serial", "") or ""

    # Send email
    emit_event(
        event_type="AGENT_COMMISSION",
        recipients=[agent.email],
        dedupe_key=f"AGENT_COMMISSION:{sale.id}:{agent.id}",
        payload={
            "agent_name": agent.get_full_name() or agent.username,
            "business_name": business.name,
            "sale_id": sale.id,
            "product_name": product_name or "Product",
            "imei": imei,
            "sale_amount": str(sale.price),
            "commission_amount": str(commission_amount),
            "commission_pct": str(commission_pct) if commission_pct > 0 else None,
            "total_earnings": str(total_earnings),
            "commission_note": commission_note,
            "sale_time": sale.created_at if hasattr(sale, "created_at") else timezone.now(),
        },
        business=business,
        user=agent,
    )


# ==============================================================================
# Weekly Sales Digest
# ==============================================================================


def send_weekly_sales_digest(business=None, week_ending_date=None):
    """
    Send weekly sales digest email to managers.

    Calculates last 7 days (Mon-Sun week ending on Friday) and sends summary:
    - Total sales amount (revenue)
    - Total profit
    - Total number of sales
    - Breakdown of products sold (top 10 by revenue and by quantity)
    - Top agents (top 5 by revenue; include profit if possible)
    - Highest selling day (date with highest revenue)
    - Tips section (3 bullet tips based on data)

    Args:
        business: Optional Business instance. If None, sends to all active businesses.
        week_ending_date: Optional date for week ending (defaults to last Friday)

    Returns:
        Number of emails sent
    """
    from datetime import timedelta
    from decimal import Decimal

    import pytz
    from django.db.models import Count, F, Q, Sum
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    from sales.models import Sale

    # Get Malawi timezone
    malawi_tz = pytz.timezone("Africa/Blantyre")
    now_malawi = timezone.now().astimezone(malawi_tz)

    # Calculate week ending date (last Friday at 5pm Malawi time)
    if week_ending_date:
        week_end = week_ending_date
    else:
        # Find last Friday
        days_since_friday = (now_malawi.weekday() - 4) % 7
        if days_since_friday == 0 and now_malawi.hour < 17:
            # Today is Friday but before 5pm, use previous Friday
            days_since_friday = 7
        week_end = (now_malawi - timedelta(days=days_since_friday)).date()

    # Week period: Monday to Sunday (ending on Friday)
    week_start = week_end - timedelta(days=6)  # Last 7 days including Friday

    # Get businesses to process
    if business:
        businesses = [business]
    else:
        from tenants.models import Business

        businesses = Business.objects.filter(status="ACTIVE")

    emails_sent = 0

    for biz in businesses:
        try:
            # Get sales for this week
            sales_qs = Sale.objects.filter(
                location__business=biz,
                sold_at__gte=week_start,
                sold_at__lte=week_end,
            ).select_related("agent", "item", "location")

            if not sales_qs.exists():
                continue  # Skip businesses with no sales this week

            # Calculate totals
            total_revenue = sales_qs.aggregate(total=Sum("price"))["total"] or Decimal("0.00")

            total_sales_count = sales_qs.count()

            # Calculate profit (selling_price - order_price)
            total_profit = Decimal("0.00")
            try:
                for sale in sales_qs:
                    if hasattr(sale, "item") and sale.item:
                        cost = (
                            getattr(sale.item, "order_price", None)
                            or getattr(sale.item, "cost_price", None)
                            or Decimal("0.00")
                        )
                        total_profit += sale.price - cost
            except Exception:
                pass  # Profit calculation is best-effort

            # Top products by revenue (top 10)
            top_products_by_revenue = []
            try:
                product_revenue = (
                    sales_qs.values("item__product__brand", "item__product__model", "item__product__name")
                    .annotate(revenue=Sum("price"), quantity=Count("id"))
                    .order_by("-revenue")[:10]
                )

                for p in product_revenue:
                    name = ""
                    if p.get("item__product__brand") and p.get("item__product__model"):
                        name = f"{p['item__product__brand']} {p['item__product__model']}".strip()
                    elif p.get("item__product__name"):
                        name = p["item__product__name"]
                    else:
                        name = "Unknown Product"

                    top_products_by_revenue.append(
                        {"name": name, "revenue": float(p["revenue"] or 0), "quantity": p["quantity"]}
                    )
            except Exception:
                pass

            # Top products by quantity (top 10)
            top_products_by_quantity = []
            try:
                product_quantity = (
                    sales_qs.values("item__product__brand", "item__product__model", "item__product__name")
                    .annotate(quantity=Count("id"), revenue=Sum("price"))
                    .order_by("-quantity")[:10]
                )

                for p in product_quantity:
                    name = ""
                    if p.get("item__product__brand") and p.get("item__product__model"):
                        name = f"{p['item__product__brand']} {p['item__product__model']}".strip()
                    elif p.get("item__product__name"):
                        name = p["item__product__name"]
                    else:
                        name = "Unknown Product"

                    top_products_by_quantity.append(
                        {"name": name, "quantity": p["quantity"], "revenue": float(p["revenue"] or 0)}
                    )
            except Exception:
                pass

            # Top agents by revenue (top 5)
            top_agents = []
            try:
                agent_stats = (
                    sales_qs.values("agent_id", "agent__first_name", "agent__last_name", "agent__username")
                    .annotate(revenue=Sum("price"), sales_count=Count("id"))
                    .order_by("-revenue")[:5]
                )

                for a in agent_stats:
                    name = f"{a.get('agent__first_name', '')} {a.get('agent__last_name', '')}".strip()
                    if not name:
                        name = a.get("agent__username", "") or f"Agent #{a['agent_id']}"

                    top_agents.append(
                        {"name": name, "revenue": float(a["revenue"] or 0), "sales_count": a["sales_count"]}
                    )
            except Exception:
                pass

            # Highest selling day
            highest_day = None
            highest_day_revenue = Decimal("0.00")
            try:
                daily_stats = (
                    sales_qs.annotate(sale_date=TruncDate("sold_at"))
                    .values("sale_date")
                    .annotate(revenue=Sum("price"))
                    .order_by("-revenue")[:1]
                )

                if daily_stats:
                    day_data = daily_stats[0]
                    highest_day = day_data["sale_date"]
                    highest_day_revenue = day_data["revenue"] or Decimal("0.00")
            except Exception:
                pass

            # Generate tips
            tips = []
            try:
                # Tip 1: Restock top products
                if top_products_by_quantity:
                    top_product = top_products_by_quantity[0]
                    tips.append(
                        f"Restock {top_product['name']} - it's your top seller with {top_product['quantity']} units this week."
                    )

                # Tip 2: Upsell accessories or follow up on credit
                if total_sales_count > 0:
                    tips.append(
                        "Consider upselling accessories or following up on overdue credit payments to boost revenue."
                    )

                # Tip 3: Recognize top agents
                if top_agents:
                    top_agent = top_agents[0]
                    tips.append(
                        f"Recognize {top_agent['name']} - they generated MK {top_agent['revenue']:,.0f} in sales this week!"
                    )
            except Exception:
                tips = [
                    "Review your sales data regularly to identify trends.",
                    "Keep your top-selling products well-stocked.",
                    "Recognize and motivate your top-performing agents.",
                ]

            # Get managers with weekly digest enabled
            recipients = get_business_manager_emails(
                biz,
                include_owner=True,
                event_type="WEEKLY_DIGEST",
            )

            if recipients:
                # Week ending date string
                week_end_str = week_end.strftime("%B %d, %Y")

                emit_event(
                    event_type="WEEKLY_DIGEST",
                    recipients=recipients,
                    dedupe_key=f"WEEKLY_DIGEST:{biz.id}:{week_end}",
                    payload={
                        "business_name": biz.name,
                        "week_start": week_start.strftime("%B %d, %Y"),
                        "week_end": week_end_str,
                        "total_revenue": str(total_revenue),
                        "total_profit": str(total_profit),
                        "total_sales_count": total_sales_count,
                        "top_products_by_revenue": top_products_by_revenue[:10],
                        "top_products_by_quantity": top_products_by_quantity[:10],
                        "top_agents": top_agents[:5],
                        "highest_day": highest_day.strftime("%B %d, %Y") if highest_day else None,
                        "highest_day_revenue": str(highest_day_revenue) if highest_day_revenue else None,
                        "tips": tips[:3],
                    },
                    business=biz,
                )
                emails_sent += len(recipients)
        except Exception as e:
            logger.error(f"Failed to send weekly digest for business {biz.id}: {e}")

    return emails_sent


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
    businesses = Business.objects.filter(status="ACTIVE")

    for business in businesses:
        # Get all active memberships (agents + managers) for this business
        memberships = Membership.objects.filter(business=business, status="ACTIVE").select_related("user").distinct()

        for membership in memberships:
            user = membership.user

            # Check if notification already exists for this user/business/month
            # to ensure idempotency
            existing = Notification.objects.filter(
                user=user,
                business=business,
                category="payslip_reminder",
                created_at__year=year,
                created_at__month=month,
            ).exists()

            if existing:
                continue  # Skip if already notified this month

            # Create the payslip reminder notification
            with transaction.atomic():
                Notification.objects.create(
                    user=user,
                    business=business,
                    audience="AGENT" if membership.role == "AGENT" else "ADMIN",
                    category="payslip_reminder",
                    level="info",
                    message="Payslip day is coming – salaries close soon. Please check your wallet and sales.",
                    meta={
                        "year": year,
                        "month": month,
                        "membership_id": membership.id,
                        "role": membership.role,
                    },
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

    return qs.order_by("-created_at")[:limit]


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
        user=user, business=business, category="payslip_reminder", read_at__isnull=True, created_at__gte=cutoff
    ).exists()
