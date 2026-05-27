# inventory/tasks_gym_emails.py
"""
Celery tasks for gym email notifications.
All tasks use Africa/Blantyre timezone for scheduling.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

import pytz
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import models
from django.template.loader import render_to_string
from django.utils import timezone

from inventory.models_verticals import GymCheckIn, GymMember, GymMemberStatus, GymPayment
from tenants.models import Business, Membership

logger = logging.getLogger(__name__)

# Malawi timezone
MALAWI_TZ = pytz.timezone("Africa/Blantyre")


@shared_task
def send_gym_inactivity_reminders():
    """
    Daily task: Send reminders to members who missed 2+ days of check-ins.
    Scheduled to run at 3:00 PM Malawi time (Africa/Blantyre).

    Eligibility:
    - Member has email
    - Member has ACTIVE membership (not expired)
    - Last check-in date <= today-2 OR never checked in and membership age >= 2 days
    - last_inactivity_reminder_at is not today (avoid spam)
    """
    try:
        today = timezone.now().astimezone(MALAWI_TZ).date()
        two_days_ago = today - timedelta(days=2)

        logger.info(f"[Gym Inactivity Reminders] Starting for date: {today}")

        # Get all businesses with gym members
        businesses = Business.objects.filter(gym_members__isnull=False).distinct()

        total_sent = 0
        total_skipped = 0

        for business in businesses:
            # Get active members with email
            members = GymMember.objects.filter(
                business=business,
                is_active=True,
                is_archived=False,
                status=GymMemberStatus.ACTIVE,
                membership_end__gte=today,
                email__isnull=False,
            ).exclude(email="")

            for member in members:
                # Check membership age
                if member.membership_start:
                    membership_age_days = (today - member.membership_start).days
                    if membership_age_days < 2:
                        total_skipped += 1
                        continue

                # Check if already reminded today
                if hasattr(member, "last_inactivity_reminder_at") and member.last_inactivity_reminder_at == today:
                    total_skipped += 1
                    continue

                # Get member's last check-in
                last_checkin = (
                    GymCheckIn.objects.filter(business=business, member=member).order_by("-timestamp").first()
                )

                should_remind = False

                if not last_checkin:
                    # Never checked in and membership age >= 2
                    should_remind = True
                else:
                    # Convert check-in timestamp to Malawi timezone for accurate date comparison
                    last_checkin_date = last_checkin.timestamp.astimezone(MALAWI_TZ).date()
                    if last_checkin_date <= two_days_ago:
                        # Last check-in was 2+ days ago
                        should_remind = True

                if should_remind:
                    try:
                        # Send reminder email
                        subject = f"We missed you at {business.name} 💪"

                        context = {
                            "member": member,
                            "business": business,
                            "days_missed": (today - last_checkin.timestamp.date()).days if last_checkin else "several",
                        }

                        message = render_to_string("emails/gym_inactivity_reminder.html", context)
                        plain_message = render_to_string("emails/gym_inactivity_reminder.txt", context)

                        send_mail(
                            subject=subject,
                            message=plain_message,
                            html_message=message,
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[member.email],
                            fail_silently=True,
                        )

                        # Update last reminder date (if field exists)
                        if hasattr(member, "last_inactivity_reminder_at"):
                            member.last_inactivity_reminder_at = today
                            member.save(update_fields=["last_inactivity_reminder_at"])

                        total_sent += 1
                        logger.info(f"  Sent reminder to {member.name} ({member.email})")

                    except Exception as e:
                        logger.error(f"  Failed to send reminder to {member.name}: {e}")
                        continue
                else:
                    total_skipped += 1

        logger.info(f"[Gym Inactivity Reminders] Complete: {total_sent} sent, {total_skipped} skipped")
        return {"sent": total_sent, "skipped": total_skipped}

    except Exception as e:
        logger.error(f"[Gym Inactivity Reminders] Error: {e}", exc_info=True)
        raise


@shared_task
def send_gym_weekly_manager_summary():
    """
    Weekly task: Send KPI summary to managers every Monday at 3:00 PM Malawi time.

    Metrics included:
    - Active members
    - New members this week
    - Total check-ins this week
    - Attendance rate
    - Missed 2+ days count
    - Revenue from memberships (week)
    - Upcoming renewals (next 7 days)
    """
    try:
        today = timezone.now().astimezone(MALAWI_TZ).date()
        week_start = today - timedelta(days=7)
        seven_days_from_now = today + timedelta(days=7)

        logger.info(f"[Gym Weekly Manager Summary] Starting for week ending: {today}")

        # Get all businesses with gym members
        businesses = Business.objects.filter(gym_members__isnull=False).distinct()

        total_sent = 0

        for business in businesses:
            # Get managers for this business
            managers = Membership.objects.filter(
                business=business, is_active=True, role__in=["MANAGER", "OWNER"]
            ).select_related("user")

            manager_emails = [m.user.email for m in managers if m.user and m.user.email]

            if not manager_emails:
                logger.info(f"  No managers with email for {business.name}, skipping")
                continue

            # Calculate KPIs
            members_qs = GymMember.objects.filter(business=business, is_archived=False)

            # Active members
            active_members = members_qs.filter(membership_end__gte=today, status=GymMemberStatus.ACTIVE).count()

            # New members this week
            week_start_dt = timezone.make_aware(
                timezone.datetime.combine(week_start, timezone.datetime.min.time()), timezone=MALAWI_TZ
            )
            today_end_dt = timezone.make_aware(
                timezone.datetime.combine(today + timedelta(days=1), timezone.datetime.min.time()), timezone=MALAWI_TZ
            )

            new_members = members_qs.filter(joined_at__gte=week_start_dt, joined_at__lt=today_end_dt).count()

            # Total check-ins this week
            checkins_this_week = GymCheckIn.objects.filter(
                business=business, timestamp__gte=week_start_dt, timestamp__lt=today_end_dt
            ).count()

            # Attendance rate (check-ins / (active_members * 7))
            if active_members > 0:
                attendance_rate = (checkins_this_week / (active_members * 7)) * 100
            else:
                attendance_rate = 0

            # Missed 2+ days
            two_days_ago = today - timedelta(days=2)
            missed_2_days = 0
            active_member_objs = members_qs.filter(membership_end__gte=today, status=GymMemberStatus.ACTIVE)

            for member in active_member_objs:
                membership_age_days = (today - member.membership_start).days if member.membership_start else 0
                if membership_age_days < 2:
                    continue

                last_checkin = (
                    GymCheckIn.objects.filter(business=business, member=member).order_by("-timestamp").first()
                )

                if not last_checkin or last_checkin.timestamp.date() <= two_days_ago:
                    missed_2_days += 1

            # Revenue this week
            from django.db.models import Sum

            revenue_this_week = GymPayment.objects.filter(
                member__business=business, paid_at__gte=week_start_dt, paid_at__lt=today_end_dt, is_active=True
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

            # Upcoming renewals (next 7 days)
            upcoming_renewals = members_qs.filter(
                membership_end__gte=today, membership_end__lte=seven_days_from_now, status=GymMemberStatus.ACTIVE
            ).count()

            # Send email
            try:
                subject = f"Weekly Gym Report - {business.name} ({today})"

                context = {
                    "business": business,
                    "week_start": week_start,
                    "week_end": today,
                    "active_members": active_members,
                    "new_members": new_members,
                    "checkins_this_week": checkins_this_week,
                    "attendance_rate": round(attendance_rate, 1),
                    "missed_2_days": missed_2_days,
                    "revenue_this_week": revenue_this_week,
                    "upcoming_renewals": upcoming_renewals,
                }

                message = render_to_string("emails/gym_weekly_manager_summary.html", context)
                plain_message = render_to_string("emails/gym_weekly_manager_summary.txt", context)

                send_mail(
                    subject=subject,
                    message=plain_message,
                    html_message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=manager_emails,
                    fail_silently=True,
                )

                total_sent += 1
                logger.info(f"  Sent weekly summary to {len(manager_emails)} manager(s) for {business.name}")

            except Exception as e:
                logger.error(f"  Failed to send weekly summary for {business.name}: {e}")
                continue

        logger.info(f"[Gym Weekly Manager Summary] Complete: {total_sent} businesses notified")
        return {"sent": total_sent}

    except Exception as e:
        logger.error(f"[Gym Weekly Manager Summary] Error: {e}", exc_info=True)
        raise


@shared_task
def notify_gym_payment_to_managers(payment_id: int):
    """
    Instant task: Send email to managers when a membership payment is recorded.

    Args:
        payment_id: ID of the GymPayment that was just created
    """
    try:
        payment = GymPayment.objects.select_related("member", "member__business", "trainer", "paid_by").get(
            id=payment_id
        )

        business = payment.member.business

        # Get managers for this business
        managers = Membership.objects.filter(
            business=business, is_active=True, role__in=["MANAGER", "OWNER"]
        ).select_related("user")

        manager_emails = [m.user.email for m in managers if m.user and m.user.email]

        if not manager_emails:
            logger.info(f"No managers with email for {business.name}, skipping payment notification")
            return {"sent": 0}

        # Send email
        subject = f"💰 New Payment: {payment.member.name} - {business.name}"

        context = {
            "payment": payment,
            "member": payment.member,
            "business": business,
        }

        message = render_to_string("emails/gym_payment_notification.html", context)
        plain_message = render_to_string("emails/gym_payment_notification.txt", context)

        send_mail(
            subject=subject,
            message=plain_message,
            html_message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=manager_emails,
            fail_silently=True,
        )

        logger.info(f"Sent payment notification to {len(manager_emails)} manager(s) for {business.name}")
        return {"sent": len(manager_emails)}

    except GymPayment.DoesNotExist:
        logger.error(f"Payment {payment_id} not found")
        return {"sent": 0, "error": "Payment not found"}
    except Exception as e:
        logger.error(f"Failed to send payment notification for payment {payment_id}: {e}", exc_info=True)
        raise
