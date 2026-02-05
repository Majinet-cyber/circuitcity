# inventory/views_gym.py
"""
Views for gym operations: member management, payments, 30-day memberships.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import manager_required
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models_verticals import (
    GymCheckIn,
    GymMember,
    GymMemberAction,
    GymMemberLog,
    GymMemberStatus,
    GymPayment,
    GymSettings,
    GymTrainer,
    GymWalletEntry,
    TrainerFee,
)
from tenants.utils import require_business

# ==============================================================================
# GYM MEMBER CRUD
# ==============================================================================


class GymMemberForm(forms.ModelForm):
    """Form for adding/editing gym members with editable fees"""

    mark_as_paid = forms.BooleanField(
        required=False, initial=False, label="Mark as paid now", help_text="Check to activate membership for 30 days"
    )
    membership_fee = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        label="Membership Fee (MWK)",
        help_text="Monthly membership fee (editable)",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "e.g., 55000.00", "min": "0"}
        ),
    )
    trainer_fee = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        label="Trainer Fee (MWK)",
        help_text="Optional trainer fee if trainer is assigned",
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.01", "placeholder": "e.g., 20000.00", "min": "0"}
        ),
    )

    class Meta:
        model = GymMember
        fields = ["name", "phone", "email", "trainer", "notes"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Member name",
                    "pattern": "[A-Za-z\\s\\-']+",
                    "title": "Please enter letters only",
                }
            ),
            "phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Phone number", "type": "tel", "inputmode": "tel"}
            ),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email (optional)"}),
            "trainer": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Additional notes (optional)"}
            ),
        }
        labels = {
            "trainer": "Assign Trainer (optional)",
        }

    def __init__(self, business=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if business:
            self.fields["trainer"].queryset = GymTrainer.objects.filter(business=business, is_active=True).order_by(
                "name"
            )
        self.fields["trainer"].required = False

    def clean_name(self):
        """Validate member name (text only, no digits)"""
        from core.validators import validate_no_digits
        name = self.cleaned_data.get("name", "").strip()
        if name:
            validate_no_digits(name)
        return name

    def clean_phone(self):
        """Validate phone number format"""
        from core.validators import validate_phone_number_format, clean_phone_number
        phone = self.cleaned_data.get("phone", "").strip()
        if phone:
            validate_phone_number_format(phone)
            # Clean and normalize

            phone = clean_phone_number(phone)
        return phone


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def members_list(request):
    """List all gym members"""
    business = get_active_business(request)

    # Filter: active, archived, or all
    filter_type = request.GET.get("filter", "active")
    members = GymMember.objects.filter(business=business)

    if filter_type == "active":
        members = members.filter(is_active=True, is_archived=False)
    elif filter_type == "archived":
        members = members.filter(is_archived=True)
    # else: show all

    members = members.order_by("-joined_at")

    return render(
        request,
        "inventory/gym/members_list.html",
        {
            "active_tab": "members",  # For navigation highlighting
            "members": members,
            "business": business,
            "filter_type": filter_type,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def member_add(request):
    """Add a new gym member"""
    business = get_active_business(request)

    # Get gym settings for default fees
    try:
        gym_settings = GymSettings.objects.get(business=business)
    except GymSettings.DoesNotExist:
        gym_settings = GymSettings.objects.create(business=business)

    # Set initial fee values from settings
    initial_data = {
        "membership_fee": gym_settings.default_membership_price,
        "trainer_fee": gym_settings.default_trainer_fee,
    }

    if request.method == "POST":
        form = GymMemberForm(business, request.POST)
        if form.is_valid():
            with transaction.atomic():
                member = form.save(commit=False)
                member.business = business

                # Set fees from form (editable) or defaults from settings
                member.membership_fee = form.cleaned_data.get("membership_fee") or gym_settings.default_membership_price

                # Set has_trainer based on whether a trainer is assigned
                if member.trainer:
                    member.has_trainer = True
                    member.trainer_fee = form.cleaned_data.get("trainer_fee") or gym_settings.default_trainer_fee
                else:
                    member.has_trainer = False
                    member.trainer_fee = Decimal("0.00")

                member.save()

                # If marked as paid, activate membership for 30 days
                mark_as_paid = form.cleaned_data.get("mark_as_paid", False)
                if mark_as_paid:
                    member.set_paid(
                        payment_date=None,  # Today
                        membership_fee=member.membership_fee,
                        trainer_fee=member.trainer_fee,
                        paid_by=request.user,
                    )
                    messages.success(
                        request,
                        f"Member '{member.name}' added and activated. Membership valid until {member.membership_end.strftime('%Y-%m-%d')}.",
                    )
                else:
                    member.status = GymMemberStatus.PENDING_PAYMENT
                    member.save(update_fields=["status"])
                    messages.success(
                        request, f"Member '{member.name}' added. Remember to mark as paid when payment is received."
                    )

                # Log the creation
                GymMemberLog.objects.create(
                    member=member,
                    action=GymMemberAction.CREATED,
                    changes={
                        "name": member.name,
                        "phone": member.phone,
                        "email": member.email,
                        "trainer": member.trainer.name if member.trainer else None,
                        "marked_as_paid": mark_as_paid,
                    },
                    performed_by=request.user,
                )

                # Send QR code PDF email if member has email (after transaction commit)
                if member.email:
                    from inventory.services.gym_qr_email import send_member_qr_email

                    transaction.on_commit(lambda: send_member_qr_email(member, request))

            return redirect("gym:member_detail", member_id=member.id)
    else:
        form = GymMemberForm(business, initial=initial_data)

    return render(
        request,
        "inventory/gym/member_form.html",
        {
            "form": form,
            "business": business,
            "gym_settings": gym_settings,
            "title": "Add New Member",
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def member_edit(request, member_id):
    """Edit an existing gym member"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)

    if request.method == "POST":
        form = GymMemberForm(business, request.POST, instance=member)
        if form.is_valid():
            # Track what changed
            changes = {}
            for field in ["name", "phone", "email", "notes"]:
                old_val = getattr(member, field)
                new_val = form.cleaned_data.get(field)
                if old_val != new_val:
                    changes[field] = {"old": old_val, "new": new_val}

            with transaction.atomic():
                member = form.save()

                # Log the update
                if changes:
                    GymMemberLog.objects.create(
                        member=member, action=GymMemberAction.UPDATED, changes=changes, performed_by=request.user
                    )

            messages.success(request, f"Member '{member.name}' updated successfully.")
            return redirect("gym:member_detail", member_id=member.id)
    else:
        # IMPORTANT: On edit, show member's existing fees (NOT defaults from settings)
        initial_data = {
            "membership_fee": member.membership_fee,
            "trainer_fee": member.trainer_fee,
        }
        form = GymMemberForm(business, instance=member, initial=initial_data)

    return render(
        request,
        "inventory/gym/member_form.html",
        {
            "form": form,
            "member": member,
            "business": business,
            "title": "Edit Member",
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def member_detail(request, member_id):
    """View member details with payment history and logs"""
    try:
        from inventory.utils_gym import GYM_MEMBERSHIP_DAYS, get_membership_status
    except ImportError:
        # Fallback if utils_gym not available
        def get_membership_status(member):
            return {"status_code": "unknown", "status_label": "Unknown"}

        GYM_MEMBERSHIP_DAYS = 30

    business = get_active_business(request)

    # Safely get member with proper error handling
    try:
        member = get_object_or_404(GymMember, pk=member_id, business=business)
    except Exception as e:
        messages.error(request, f"Member not found or inaccessible: {str(e)}")
        return redirect("gym:members_list")

    # Get accurate membership status with fallback
    try:
        membership_status = get_membership_status(member)
        if not membership_status or not isinstance(membership_status, dict):
            membership_status = {"status_code": "unknown", "status_label": "Unknown"}
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error getting membership status for member {member_id}: {e}", exc_info=True)
        membership_status = {"status_code": "error", "status_label": "Error loading status"}

    # Get payment history safely
    try:
        payments = member.payments.select_related("paid_by").order_by("-paid_at")
    except Exception:
        payments = []

    # Get logs safely
    try:
        logs = member.logs.select_related("performed_by").order_by("-created_at")
    except Exception:
        logs = []

    # Get gym settings for contact info
    try:
        gym_settings = GymSettings.objects.get(business=business)
    except GymSettings.DoesNotExist:
        gym_settings = None
    except Exception:
        gym_settings = None

    # Check for missing trainer fee
    trainer_fee_missing = False
    try:
        if getattr(member, "trainer", None) and membership_status.get("status_code") == "active":
            # Check if there's a trainer fee for current period
            start_date = membership_status.get("start_date")
            end_date = membership_status.get("end_date")
            if start_date and end_date:
                trainer_fee_missing = not TrainerFee.objects.filter(
                    member=member, period_start=start_date, period_end=end_date
                ).exists()
    except Exception:
        # TrainerFee table may not exist yet or other error
        trainer_fee_missing = False

    # Safely get member properties with fallbacks
    try:
        member_joined_at = member.joined_at if hasattr(member, "joined_at") and member.joined_at else None
    except Exception:
        member_joined_at = None

    try:
        member_membership_end = (
            member.membership_end if hasattr(member, "membership_end") and member.membership_end else None
        )
    except Exception:
        member_membership_end = None

    try:
        member_days_left = getattr(member, "days_left", None)
        if member_days_left is None:
            member_days_left = 0
    except Exception:
        member_days_left = 0

    try:
        member_duration_days = getattr(member, "duration_days", GYM_MEMBERSHIP_DAYS)
        if member_duration_days is None:
            member_duration_days = GYM_MEMBERSHIP_DAYS
    except Exception:
        member_duration_days = GYM_MEMBERSHIP_DAYS

    try:
        member_next_payment_date = getattr(member, "next_payment_date_property", None)
    except Exception:
        member_next_payment_date = None

    try:
        member_is_active = getattr(member, "is_active_membership", False)
    except Exception:
        member_is_active = False

    try:
        member_days_attended = getattr(member, "days_attended", 0)
        if member_days_attended is None:
            member_days_attended = 0
    except Exception:
        member_days_attended = 0

    try:
        member_code = getattr(member, "member_code", None)
        # Ensure qr_uuid exists (will be auto-generated on save if missing)
        if not member.qr_uuid:
            member.save(update_fields=["qr_uuid"])  # This will trigger auto-generation in save()
            member.refresh_from_db()
    except Exception:
        member_code = None

    try:
        member_qr_code = getattr(member, "get_qr_code_data_url", None)
        if callable(member_qr_code):
            member_qr_code = member_qr_code()
        if not member_qr_code:
            member_qr_code = None
    except Exception:
        member_qr_code = None

    try:
        member_trainer = getattr(member, "trainer", None)
    except Exception:
        member_trainer = None

    return render(
        request,
        "inventory/gym/member_detail.html",
        {
            "member": member,
            "membership_status": membership_status,
            "payments": payments,
            "logs": logs,
            "gym_settings": gym_settings,
            "business": business,
            "trainer_fee_missing": trainer_fee_missing,
            "total_days": GYM_MEMBERSHIP_DAYS,
            # Safe member properties
            "member_joined_at": member_joined_at,
            "member_membership_end": member_membership_end,
            "member_days_left": member_days_left,
            "member_duration_days": member_duration_days,
            "member_next_payment_date": member_next_payment_date,
            "member_is_active": member_is_active,
            "member_days_attended": member_days_attended,
            "member_code": member_code,
            "member_qr_code": member_qr_code,
            "member_trainer": member_trainer,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
@require_POST
def member_archive(request, member_id):
    """Archive a gym member"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)

    with transaction.atomic():
        member.archive(request.user)

        # Log the archival
        GymMemberLog.objects.create(
            member=member,
            action=GymMemberAction.ARCHIVED,
            changes={"archived_at": str(timezone.now())},
            performed_by=request.user,
        )

    messages.success(request, f"Member '{member.name}' archived.")
    return redirect("gym:members_list")


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
@require_POST
def member_restore(request, member_id):
    """Restore an archived member"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)

    with transaction.atomic():
        member.is_archived = False
        member.is_active = True
        member.archived_at = None
        member.archived_by = None
        member.save(update_fields=["is_archived", "is_active", "archived_at", "archived_by"])

        # Log the restoration
        GymMemberLog.objects.create(
            member=member,
            action=GymMemberAction.RESTORED,
            changes={"restored_at": str(timezone.now())},
            performed_by=request.user,
        )

    messages.success(request, f"Member '{member.name}' restored.")
    return redirect("gym:member_detail", member_id=member.id)


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
@require_POST
def member_set_paid(request, member_id):
    """Mark a member as paid / renew membership with prorated days based on default fee"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)

    # Get gym settings for fees
    try:
        gym_settings = GymSettings.objects.get(business=business)
    except GymSettings.DoesNotExist:
        gym_settings = GymSettings.objects.create(business=business)

    with transaction.atomic():
        # Update fees based on current settings
        member.membership_fee = gym_settings.default_membership_price
        if member.has_trainer:
            member.trainer_fee = gym_settings.default_trainer_fee
        else:
            member.trainer_fee = Decimal("0.00")

        # Calculate total amount
        total_amount = member.membership_fee + member.trainer_fee

        # Set as paid (activates with prorated days based on amount)
        member.set_paid(
            payment_date=None,  # Today
            membership_fee=member.membership_fee,
            trainer_fee=member.trainer_fee,
            paid_by=request.user,
            amount=total_amount,
        )

        # Calculate days granted for message
        from inventory.utils_gym import calculate_prorated_days

        days_granted = calculate_prorated_days(total_amount)

        # Log the renewal
        GymMemberLog.objects.create(
            member=member,
            action=GymMemberAction.UPDATED,
            changes={
                "action": "renewed",
                "membership_start": str(member.membership_start),
                "membership_end": str(member.membership_end),
                "amount": str(total_amount),
                "days_granted": days_granted,
            },
            performed_by=request.user,
        )

    messages.success(
        request,
        f"Member '{member.name}' renewed. {days_granted} days granted. Membership valid until {member.membership_end.strftime('%Y-%m-%d')}.",
    )
    return redirect("gym:member_detail", member_id=member.id)


# ==============================================================================
# GYM CHECK-INS
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def checkin_page(request):
    """Dedicated check-in page showing all members with attendance tracking"""
    from inventory.utils_gym import GYM_MEMBERSHIP_DAYS, get_membership_status

    business = get_active_business(request)
    today = timezone.now().date()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Get all active members
    members = (
        GymMember.objects.filter(business=business, is_active=True, is_archived=False)
        .select_related("trainer")
        .order_by("name")
    )

    # Build member data with attendance
    member_data = []
    for member in members:
        # Use centralized properties for membership status
        is_active = member.is_active_membership
        days_left = member.days_left
        total_days = member.duration_days
        status_label = member.status_label
        next_payment = member.next_payment_date_property

        # Check if member checked in today
        checked_in_today = GymCheckIn.objects.filter(
            business=business, member=member, timestamp__gte=today_start
        ).exists()

        # Calculate days attended in current period
        days_attended = member.days_attended()

        # Determine "Today" column value
        if checked_in_today:
            today_status = "present"
            today_label = "Present"
        elif is_active:
            today_status = "absent"
            today_label = "Absent"
        else:
            today_status = "inactive"
            today_label = "Inactive"

        # Get gamification data
        badge_display = member.get_badge_display()

        member_data.append(
            {
                "member": member,
                "status_label": status_label,
                "is_active": is_active,
                "days_left": days_left,
                "total_days": total_days,
                "days_attended": days_attended,
                "next_payment": next_payment,
                "checked_in_today": checked_in_today,
                "today_status": today_status,
                "today_label": today_label,
                # Gamification
                "streak_days": member.streak_days,
                "monthly_checkins": member.monthly_checkins,
                "badge_display": badge_display,
            }
        )

    return render(
        request,
        "inventory/gym/checkin_page.html",
        {
            "active_tab": "checkins",  # For navigation highlighting
            "member_data": member_data,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@require_POST
def member_checkin(request, member_id):
    """Check in a gym member with gamification"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)

    # Check if already checked in today
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = GymCheckIn.objects.filter(business=business, member=member, timestamp__gte=today_start).exists()

    if existing:
        messages.info(request, f"Member '{member.name}' already checked in today.")
        celebration_data = None
    else:
        # Store old stats for comparison
        old_streak = member.streak_days
        old_badge = member.badge_level

        # Create check-in
        checkin = GymCheckIn.objects.create(
            business=business, member=member, checked_in_by=request.user, notes=request.POST.get("notes", "")
        )

        # Update gamification stats
        member.update_checkin_stats(checkin_date=timezone.now().date())

        # Refresh from DB
        member.refresh_from_db()

        # Success message with gamification feedback
        badge_info = member.get_badge_display()
        streak_msg = f" 🔥 {member.streak_days}-day streak!" if member.streak_days > 1 else ""
        badge_msg = f" {badge_info['icon']} {badge_info['label']}!" if badge_info["icon"] else ""

        messages.success(request, f"✓ {member.name} checked in!{streak_msg}{badge_msg}")

        # Prepare celebration data for modal (if milestone reached)
        celebration_data = None
        show_celebration = False

        # Check for celebration-worthy events
        badges_earned = []
        if old_badge != member.badge_level and member.badge_level != "none":
            badges_earned.append(
                {
                    "icon": badge_info["icon"],
                    "name": badge_info["label"],
                    "description": f"Earned for {member.total_checkins}+ check-ins!",
                }
            )
            show_celebration = True

        # Streak milestones (3, 7, 14, 30)
        if member.streak_days in [3, 7, 14, 30] and member.streak_days > old_streak:
            show_celebration = True

        # First check-in milestone
        if member.total_checkins == 1:
            show_celebration = True

        if show_celebration:
            celebration_data = {
                "show_celebration": True,
                "streak_days": member.streak_days,
                "monthly_checkins": member.monthly_checkins,
                "total_checkins": member.total_checkins,
                "badge_level": member.badge_level,
                "badge_display": badge_info,
                "badges_earned": badges_earned,
                "member_name": member.name,
            }

    # Return to checkin page or member detail based on referrer
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "gym:checkin_page"

    # Build redirect URL with celebration data if applicable
    if celebration_data and "checkin" in next_url:
        import json
        from urllib.parse import quote

        celebration_json = quote(json.dumps(celebration_data))
        return redirect(f"{reverse('gym:checkin_page')}?celebration={celebration_json}")
    elif "checkin" in next_url:
        return redirect("gym:checkin_page")
    elif "member_detail" in next_url or f"/member/{member_id}/" in next_url:
        return redirect("gym:member_detail", member_id=member.id)
    return redirect("gym:members_list")


# ==============================================================================
# GYM PAYMENTS (30-day memberships)
# ==============================================================================


class GymPaymentForm(forms.Form):
    """Form for recording a gym membership payment with optional trainer fee"""

    member = forms.ModelChoiceField(
        queryset=GymMember.objects.none(),
        widget=forms.Select(attrs={"class": "form-control", "data-cy": "gym-payment-member"}),
    )
    membership_amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=True,
        label="Membership Amount (MWK)",
        help_text="Base membership fee (days calculated from this only)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Enter amount (e.g., 55000.00)",
                "data-cy": "gym-payment-membership-amount",
            }
        ),
    )
    trainer = forms.ModelChoiceField(
        queryset=GymTrainer.objects.none(),
        required=False,
        label="Trainer (Optional)",
        widget=forms.Select(attrs={"class": "form-control", "data-cy": "gym-payment-trainer"}),
    )
    trainer_fee = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        label="Trainer Fee (MWK)",
        help_text="Additional trainer fee (does not add membership days)",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Enter trainer fee (optional)",
                "data-cy": "gym-payment-trainer-fee",
            }
        ),
    )
    payment_method = forms.ChoiceField(
        required=True,
        label="Payment Method",
        widget=forms.Select(attrs={"class": "form-control", "data-cy": "gym-payment-method"}),
    )
    start_date = forms.DateField(
        initial=date.today, widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional notes"}),
    )

    def __init__(self, business=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if business:
            self.fields["member"].queryset = GymMember.objects.filter(
                business=business, is_active=True, is_archived=False
            ).order_by("name")
            self.fields["trainer"].queryset = GymTrainer.objects.filter(business=business, is_active=True).order_by(
                "name"
            )

        # Set payment method choices from PaymentMethod
        from inventory.models_verticals import PaymentMethod

        self.fields["payment_method"].choices = PaymentMethod.choices
        self.fields["payment_method"].initial = PaymentMethod.CASH

    def clean(self):
        cleaned_data = super().clean()
        trainer = cleaned_data.get("trainer")
        trainer_fee = cleaned_data.get("trainer_fee") or Decimal("0.00")

        # If trainer is selected, trainer_fee should be > 0
        if trainer and trainer_fee <= 0:
            self.add_error("trainer_fee", "Trainer fee is required when a trainer is selected.")

        # If trainer_fee > 0, trainer must be selected
        if trainer_fee > 0 and not trainer:
            self.add_error("trainer", "Please select a trainer when specifying a trainer fee.")

        return cleaned_data


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def add_payment(request):
    """Record a new gym membership payment with optional trainer fee"""
    business = get_active_business(request)

    # Get default price from settings
    try:
        gym_settings = GymSettings.objects.get(business=business)
        default_membership_price = gym_settings.default_membership_price
    except GymSettings.DoesNotExist:
        default_membership_price = Decimal("55000.00")

    # Pre-select member if passed in query params
    preselected_member_id = request.GET.get("member")
    initial_data = {"membership_amount": default_membership_price}
    if preselected_member_id:
        initial_data["member"] = preselected_member_id

    if request.method == "POST":
        form = GymPaymentForm(business, request.POST)
        if form.is_valid():
            data = form.cleaned_data

            with transaction.atomic():
                from inventory.utils_gym import calculate_membership_period

                member = data["member"]
                membership_amount = data["membership_amount"]
                trainer = data.get("trainer")
                trainer_fee = data.get("trainer_fee") or Decimal("0.00")
                start_date = data["start_date"]
                payment_method = data["payment_method"]

                # IMPORTANT: Calculate days granted from membership_amount ONLY
                # Trainer fee does NOT grant extra days
                new_start, new_end, days_granted = calculate_membership_period(
                    amount=membership_amount,  # Only membership amount, not trainer fee
                    member=member,
                    start_date=start_date,
                    today=timezone.now().date(),
                )

                # Calculate total amount
                total_amount = membership_amount + trainer_fee

                # Create payment
                payment = GymPayment.objects.create(
                    member=member,
                    membership_amount=membership_amount,
                    trainer=trainer,
                    trainer_fee=trainer_fee,
                    amount=total_amount,
                    payment_method=payment_method,
                    start_date=new_start,
                    end_date=new_end,
                    paid_by=request.user,
                    notes=data.get("notes", "")
                    or f"{days_granted} days granted" + (f", trainer: {trainer.name}" if trainer else ""),
                )

                # Update member's membership dates
                member.last_payment_date = timezone.now().date()
                member.membership_start = new_start
                member.membership_end = new_end
                member.status = GymMemberStatus.ACTIVE

                # Update member's trainer if provided
                if trainer:
                    member.trainer = trainer

                member.save(
                    update_fields=["last_payment_date", "membership_start", "membership_end", "status", "trainer"]
                )

                # Create wallet entry for membership
                GymWalletEntry.objects.create(
                    business=business,
                    amount=total_amount,
                    description=f"Membership payment from {member.name} ({days_granted} days)"
                    + (f" + trainer fee" if trainer_fee > 0 else ""),
                    entry_type="income",
                    related_payment=payment,
                    created_by=request.user,
                )

                # Send instant payment notification to managers (async)
                try:
                    from inventory.tasks_gym_emails import notify_gym_payment_to_managers

                    notify_gym_payment_to_managers.delay(payment.id)
                except Exception as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to queue payment notification: {e}")

                # Credit trainer's wallet if trainer_fee > 0 and trainer has linked user
                if trainer and trainer_fee > 0:
                    if trainer.user:
                        try:
                            # Use the wallet transaction system to credit trainer
                            from wallet.models import Ledger, TxnType, WalletTransaction

                            WalletTransaction.objects.create(
                                ledger=Ledger.AGENT,
                                agent=trainer.user,
                                type=TxnType.BONUS,
                                amount=trainer_fee,
                                note=f"Trainer fee from {member.name} (gym)",
                                reference=f"gym_payment_{payment.id}",
                                effective_date=timezone.now().date(),
                                created_by=request.user,
                                business=business,
                                meta={
                                    "kind": "gym_trainer_fee",
                                    "member_id": member.id,
                                    "payment_id": payment.id,
                                    "member_name": member.name,
                                },
                            )
                        except Exception as e:
                            # Log error but don't fail the payment
                            import logging

                            logger = logging.getLogger(__name__)
                            logger.error(f"Failed to credit trainer wallet: {e}")

            success_msg = (
                f"Payment recorded. {days_granted} days granted. Membership valid until {new_end.strftime('%Y-%m-%d')}."
            )
            if trainer and trainer_fee > 0:
                success_msg += f" Trainer {trainer.name} credited with MWK {trainer_fee:,.2f}."

            messages.success(request, success_msg)
            return redirect("gym:member_detail", member_id=member.id)
    else:
        form = GymPaymentForm(business, initial=initial_data)

    recent_payments = (
        GymPayment.objects.filter(member__business=business)
        .select_related("member", "paid_by", "trainer")
        .order_by("-paid_at")[:10]
    )

    return render(
        request,
        "inventory/gym/payment_form.html",
        {
            "active_tab": "payment",  # For navigation highlighting
            "form": form,
            "recent_payments": recent_payments,
            "business": business,
        },
    )


# ==============================================================================
# GYM DASHBOARD
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def gym_dashboard(request):
    """Gym business dashboard with member stats, payment buckets, check-in metrics, and payment mix"""
    business = get_active_business(request)

    # Date range filtering
    from datetime import datetime

    range_param = request.GET.get("range", "today")
    today = timezone.now().date()

    if range_param == "today":
        start_date = end_date = today
        period_label = "Today"
    elif range_param == "7d":
        start_date = today - timedelta(days=6)
        end_date = today
        period_label = "Last 7 Days"
    elif range_param == "month":
        start_date = today.replace(day=1)
        end_date = today
        period_label = "This Month"
    elif range_param == "custom":
        start_str = request.GET.get("start", "")
        end_str = request.GET.get("end", "")
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            period_label = f"{start_date} to {end_date}"
        except (ValueError, TypeError):
            start_date = end_date = today
            period_label = "Today"
            range_param = "today"
    else:
        start_date = end_date = today
        period_label = "Today"
        range_param = "today"

    # Get all non-archived members
    all_members = GymMember.objects.filter(business=business, is_archived=False)

    # Categorize members by accurate membership status
    from inventory.utils_gym import get_membership_status

    pending_members = []
    behind_schedule_members = []
    active_members = []

    for member in all_members:
        status = get_membership_status(member, today)
        if status["status_code"] == "none":
            # No membership = pending payment
            pending_members.append(member)
        elif status["status_code"] == "expired":
            # Expired membership = in arrears / behind schedule
            behind_schedule_members.append(member)
        elif status["status_code"] == "active":
            # Active membership
            active_members.append(member)

    pending_count = len(pending_members)
    behind_schedule_count = len(behind_schedule_members)
    active_count = len(active_members)
    total_members = all_members.count()

    # Membership expiry metrics
    expiring_soon = all_members.filter(
        status=GymMemberStatus.ACTIVE, membership_end__gte=today, membership_end__lte=today + timedelta(days=7)
    ).count()

    expired = all_members.filter(status__in=[GymMemberStatus.BEHIND_SCHEDULE, GymMemberStatus.EXPIRED]).count()

    # Check-in metrics (today for active session, range for payment-filtered check-ins)
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_checkins = GymCheckIn.objects.filter(business=business, timestamp__gte=today_start).select_related("member")

    total_checkins = today_checkins.count()

    # Active session members (checked in today and not explicitly checked out)
    active_session_members = today_checkins.values("member").distinct().count()

    # Calculate paid vs unpaid check-ins using accurate status
    paid_checkins = 0
    unpaid_checkins = 0
    for checkin in today_checkins:
        member_status = get_membership_status(checkin.member, today)
        if member_status["status_code"] == "active":
            paid_checkins += 1
        else:
            unpaid_checkins += 1

    # Conversion percentage
    if total_checkins > 0:
        conversion_percentage = (paid_checkins / total_checkins) * 100
    else:
        conversion_percentage = 0

    # Payment mix (filtered by date range)
    from django.db.models import Count, Sum

    from inventory.models_verticals import PaymentMethod
    from inventory.services.gym_metrics import get_gym_dashboard_metrics

    start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
    end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))

    # CRITICAL FIX: Use unified metrics service for this month to ensure consistency
    # This ensures is_active=True filter is applied and all calculations use same queryset
    today = timezone.now().date()
    month_start = today.replace(day=1)
    month_metrics = get_gym_dashboard_metrics(business, month_start, today)

    # For the date range (which might be different from "this month"), calculate separately
    # but still filter by is_active=True
    payments_in_range = GymPayment.objects.filter(
        member__business=business,
        is_active=True,  # CRITICAL: Only count active payments
        paid_at__gte=start_dt,
        paid_at__lte=end_dt,
    )

    payment_mix = (
        payments_in_range.values("payment_method").annotate(count=Count("id"), total=Sum("amount")).order_by("-total")
    )

    payment_mix_list = []
    for item in payment_mix:
        payment_mix_list.append(
            {
                "method": item["payment_method"],
                "method_display": dict(GymPayment._meta.get_field("payment_method").choices).get(
                    item["payment_method"], item["payment_method"]
                ),
                "count": item["count"],
                "total": item["total"] or Decimal("0.00"),
            }
        )

    total_revenue = sum(item["total"] for item in payment_mix_list)

    # Payment by method breakdown for: today, yesterday, this month
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)

    today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    today_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    yesterday_start = timezone.make_aware(datetime.combine(yesterday, datetime.min.time()))
    yesterday_end = timezone.make_aware(datetime.combine(yesterday, datetime.max.time()))
    month_start_dt = timezone.make_aware(datetime.combine(month_start, datetime.min.time()))
    month_end_dt = timezone.make_aware(datetime.combine(today, datetime.max.time()))

    # Helper function to get payment method totals
    def get_payment_method_totals(start, end):
        payments = GymPayment.objects.filter(
            member__business=business,
            is_active=True,  # CRITICAL: Only count active payments
            paid_at__gte=start,
            paid_at__lte=end,
        )

        totals = {}
        for method_code, method_label in PaymentMethod.choices:
            method_total = payments.filter(payment_method=method_code).aggregate(total=Sum("amount"))[
                "total"
            ] or Decimal("0.00")
            totals[method_code] = {"label": method_label, "total": method_total}
        return totals

    payments_by_method_today = get_payment_method_totals(today_start, today_end)
    payments_by_method_yesterday = get_payment_method_totals(yesterday_start, yesterday_end)
    payments_by_method_month = get_payment_method_totals(month_start_dt, month_end_dt)

    # Recent payments
    recent_payments = (
        GymPayment.objects.filter(member__business=business)
        .select_related("member", "paid_by")
        .order_by("-paid_at")[:10]
    )

    # Recent check-ins
    recent_checkins = (
        GymCheckIn.objects.filter(business=business)
        .select_related("member", "checked_in_by")
        .order_by("-timestamp")[:10]
    )

    # Get gym settings
    try:
        gym_settings = GymSettings.objects.get(business=business)
    except GymSettings.DoesNotExist:
        gym_settings = None

    # Trainer earnings/ranking (filtered by date range)
    trainers = GymTrainer.objects.filter(business=business, is_active=True).order_by("name")
    trainer_stats = []
    for trainer in trainers:
        # Active members with this trainer
        active_trainer_members = trainer.members.filter(
            is_active=True, is_archived=False, status=GymMemberStatus.ACTIVE
        ).count()

        # Total trainer fees earned in date range
        trainer_fees = GymPayment.objects.filter(
            trainer=trainer, is_active=True, paid_at__gte=start_dt, paid_at__lte=end_dt
        ).aggregate(total=Sum("trainer_fee"))["total"] or Decimal("0.00")

        # Number of payments with this trainer in date range
        payment_count = GymPayment.objects.filter(
            trainer=trainer, is_active=True, paid_at__gte=start_dt, paid_at__lte=end_dt
        ).count()

        # Revenue from payments in date range where member has this trainer
        revenue = GymPayment.objects.filter(
            member__trainer=trainer,
            member__business=business,
            is_active=True,
            paid_at__gte=start_dt,
            paid_at__lte=end_dt,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        trainer_stats.append(
            {
                "trainer": trainer,
                "active_members": active_trainer_members,
                "trainer_fees": trainer_fees,
                "payment_count": payment_count,
                "revenue": revenue,
            }
        )

    # Sort by trainer fees (descending) for rankings
    trainer_ranking = sorted(trainer_stats, key=lambda x: x["trainer_fees"], reverse=True)

    # ============================================================================
    # FINANCIAL METRICS: Costs, Revenue, Profit (for today, yesterday, this month)
    # ============================================================================
    from inventory.utils_gym import get_business_costs_for_period

    # Calculate costs for different periods
    costs_today = get_business_costs_for_period(business, today, today)
    costs_yesterday = get_business_costs_for_period(business, yesterday, yesterday)
    costs_this_month = get_business_costs_for_period(business, month_start, today)

    # Calculate revenue for different periods (from GymPayment)
    # CRITICAL FIX: Calculate directly from membership_amount + trainer_fee
    # This ensures revenue is ALWAYS correct even if amount field has legacy 0/NULL values
    from django.db.models import ExpressionWrapper, F
    
    revenue_today = GymPayment.objects.filter(
        member__business=business, is_active=True, paid_at__gte=today_start, paid_at__lte=today_end
    ).aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    Coalesce(F("membership_amount"), Value(Decimal("0.00"))) +
                    Coalesce(F("trainer_fee"), Value(Decimal("0.00"))),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"] or Decimal("0.00")

    revenue_yesterday = GymPayment.objects.filter(
        member__business=business, is_active=True, paid_at__gte=yesterday_start, paid_at__lte=yesterday_end
    ).aggregate(
        total=Coalesce(
            Sum(
                ExpressionWrapper(
                    Coalesce(F("membership_amount"), Value(Decimal("0.00"))) +
                    Coalesce(F("trainer_fee"), Value(Decimal("0.00"))),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            ),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
    )["total"] or Decimal("0.00")

    # Use unified metrics service for this month to ensure consistency
    # This ensures revenue and payment_count match exactly
    revenue_this_month = month_metrics["revenue"]
    payment_count_month = month_metrics["payments_count"]

    # Calculate profit = revenue - costs
    profit_today = revenue_today - costs_today
    profit_yesterday = revenue_yesterday - costs_yesterday
    profit_this_month = revenue_this_month - costs_this_month

    # Calculate MRR (Monthly Recurring Revenue)
    # MRR = sum of active members' monthly fees (those with valid memberships)
    mrr = Decimal("0.00")
    try:
        from inventory.utils_gym import GYM_MONTHLY_FEE

        # Count active members (membership valid)
        active_members_count = all_members.filter(membership_end__gte=today).count()
        # Estimate MRR based on default monthly fee
        # (In a more sophisticated system, you'd track each member's fee)
        if gym_settings and gym_settings.default_membership_price:
            mrr = gym_settings.default_membership_price * active_members_count
        else:
            mrr = GYM_MONTHLY_FEE * active_members_count
    except Exception:
        mrr = Decimal("0.00")

    # New members this month
    new_members_this_month = GymMember.objects.filter(
        business=business, is_archived=False, joined_at__gte=month_start_dt, joined_at__lte=month_end_dt
    ).count()

    # Members per trainer (top 5)
    trainer_stats = []
    trainers = GymTrainer.objects.filter(business=business, is_active=True)
    for trainer in trainers:
        active_members_count = GymMember.objects.filter(
            business=business, trainer=trainer, is_archived=False, is_active=True
        ).count()

        # Get fees earned this month
        fees_this_month = GymPayment.objects.filter(
            member__business=business,
            member__trainer=trainer,
            trainer_fee__gt=0,
            paid_at__gte=month_start_dt,
            paid_at__lte=month_end_dt,
            is_active=True,
        ).aggregate(total=Sum("trainer_fee"))["total"] or Decimal("0.00")

        # Count payments this month
        payments_this_month = GymPayment.objects.filter(
            member__business=business,
            member__trainer=trainer,
            paid_at__gte=month_start_dt,
            paid_at__lte=month_end_dt,
            is_active=True,
        ).count()

        trainer_stats.append(
            {
                "trainer": trainer,
                "active_members": active_members_count,
                "fees_earned": fees_this_month,
                "payments_count": payments_this_month,
            }
        )

    # Sort by active members (descending) and take top 5
    trainer_stats.sort(key=lambda x: x["active_members"], reverse=True)
    top_trainers = trainer_stats[:5]

    return render(
        request,
        "inventory/gym/dashboard.html",
        {
            "business": business,
            # Date filtering
            "range_param": range_param,
            "period_label": period_label,
            "start_date": start_date,
            "end_date": end_date,
            # Payment status buckets
            "total_members": total_members,
            "pending_count": pending_count,
            "behind_schedule_count": behind_schedule_count,
            "active_count": active_count,
            "pending_members": pending_members[:10],  # Show first 10
            "behind_schedule_members": behind_schedule_members[:10],
            "active_members": active_members[:10],
            # Membership expiry metrics
            "expiring_soon": expiring_soon,
            "expired": expired,
            # Check-in metrics
            "total_checkins": total_checkins,
            "paid_checkins": paid_checkins,
            "unpaid_checkins": unpaid_checkins,
            "conversion_percentage": round(conversion_percentage, 1),
            "active_session_members": active_session_members,
            "recent_checkins": recent_checkins,
            # Payment mix - use unified metrics for "this month" to ensure consistency
            "payment_mix": month_metrics["payment_mix"],  # Use unified metrics for this month
            "total_revenue": revenue_this_month,  # Use unified revenue for this month
            # Payment by method (today, yesterday, this month)
            "payments_by_method_today": payments_by_method_today,
            "payments_by_method_yesterday": payments_by_method_yesterday,
            "payments_by_method_month": payments_by_method_month,
            # Trainer stats
            "trainer_stats": trainer_stats,
            "trainer_ranking": trainer_ranking,  # Sorted by fees earned
            "top_trainers": top_trainers,  # Top 5 trainers by active members
            # New members this month
            "new_members_this_month": new_members_this_month,
            # Financial metrics (costs, revenue, profit)
            "costs_today": costs_today,
            "costs_yesterday": costs_yesterday,
            "costs_this_month": costs_this_month,
            "revenue_today": revenue_today,
            "revenue_yesterday": revenue_yesterday,
            "revenue_this_month": revenue_this_month,
            "profit_today": profit_today,
            "profit_yesterday": profit_yesterday,
            "profit_this_month": profit_this_month,
            "payment_count_month": payment_count_month,
            "mrr": mrr,
            # For templates/verticals/gym/dashboard.html (simplified template)
            "costs": costs_this_month,  # Default to this month
            "revenue": revenue_this_month,
            "profit": profit_this_month,
            "payment_count": payment_count_month,
            # Legacy fields (for backward compatibility)
            "members_active_count": active_count,
            "members_in_arrears_count": behind_schedule_count,
            "members_in_arrears": behind_schedule_members[:10],
            "recent_payments": recent_payments,
            "gym_settings": gym_settings,
        },
    )


# ==============================================================================
# GYM SETTINGS
# ==============================================================================


class GymSettingsForm(forms.ModelForm):
    """Form for gym business settings"""

    class Meta:
        model = GymSettings
        fields = [
            "support_phone",
            "support_email",
            "default_membership_price",
            "default_trainer_fee",
            "arrears_message",
        ]
        widgets = {
            "support_phone": forms.TextInput(attrs={"class": "form-control"}),
            "support_email": forms.EmailInput(attrs={"class": "form-control"}),
            "default_membership_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "default_trainer_fee": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "arrears_message": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }
        labels = {
            "default_membership_price": "Default Membership Fee (30 days)",
            "default_trainer_fee": "Default Trainer Fee (30 days)",
        }


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
def gym_settings_view(request):
    """Manage gym settings"""
    business = get_active_business(request)

    # Get or create settings
    gym_settings, created = GymSettings.objects.get_or_create(business=business)

    # Ensure default trainers exist (idempotent)
    default_trainers = ["Lester", "Steve", "Philip", "Ben"]
    for trainer_name in default_trainers:
        GymTrainer.objects.get_or_create(
            business=business,
            name=trainer_name,
            defaults={"is_active": True}
        )

    if request.method == "POST":
        form = GymSettingsForm(request.POST, instance=gym_settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Gym settings updated.")
            return redirect("gym:settings")
    else:
        form = GymSettingsForm(instance=gym_settings)

    return render(
        request,
        "inventory/gym/settings.html",
        {
            "form": form,
            "gym_settings": gym_settings,
            "business": business,
        },
    )


# ==============================================================================
# GYM TRAINERS
# ==============================================================================


class GymTrainerForm(forms.ModelForm):
    """Form for adding/editing gym trainers"""

    class Meta:
        model = GymTrainer
        fields = ["name", "phone", "email", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Trainer name"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone number"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email (optional)"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Additional notes (optional)"}
            ),
        }


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
def trainers_list(request):
    """List all gym trainers"""
    business = get_active_business(request)

    trainers = GymTrainer.objects.filter(business=business, is_active=True).order_by("name")

    # For each trainer, compute stats
    trainer_stats = []
    for trainer in trainers:
        # Active members assigned to this trainer
        active_members = trainer.members.filter(
            is_active=True, is_archived=False, status=GymMemberStatus.ACTIVE
        ).count()

        # Total members (including pending/behind)
        total_members = trainer.members.filter(is_active=True, is_archived=False).count()

        trainer_stats.append(
            {
                "trainer": trainer,
                "active_members": active_members,
                "total_members": total_members,
            }
        )

    return render(
        request,
        "inventory/gym/trainers_list.html",
        {
            "trainer_stats": trainer_stats,
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
def trainer_add(request):
    """Add a new gym trainer"""
    business = get_active_business(request)

    if request.method == "POST":
        form = GymTrainerForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                trainer = form.save(commit=False)
                trainer.business = business
                trainer.save()

            messages.success(request, f"Trainer '{trainer.name}' added successfully.")
            return redirect("gym:trainers_list")
    else:
        form = GymTrainerForm()

    return render(
        request,
        "inventory/gym/trainer_form.html",
        {
            "form": form,
            "business": business,
            "title": "Add Trainer",
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
def trainer_edit(request, trainer_id):
    """Edit an existing gym trainer"""
    business = get_active_business(request)
    trainer = get_object_or_404(GymTrainer, pk=trainer_id, business=business)

    if request.method == "POST":
        form = GymTrainerForm(request.POST, instance=trainer)
        if form.is_valid():
            trainer = form.save()
            messages.success(request, f"Trainer '{trainer.name}' updated successfully.")
            return redirect("gym:trainers_list")
    else:
        form = GymTrainerForm(instance=trainer)

    return render(
        request,
        "inventory/gym/trainer_form.html",
        {
            "form": form,
            "trainer": trainer,
            "business": business,
            "title": "Edit Trainer",
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
@require_POST
def trainer_deactivate(request, trainer_id):
    """Deactivate a gym trainer"""
    business = get_active_business(request)
    trainer = get_object_or_404(GymTrainer, pk=trainer_id, business=business)

    trainer.is_active = False
    trainer.save(update_fields=["is_active"])

    messages.success(request, f"Trainer '{trainer.name}' deactivated.")
    return redirect("gym:trainers_list")


# ==============================================================================
# GYM MEMBER SCANNING (BARCODE/QR)
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def gym_scan_page(request):
    """
    Gym member barcode/QR scanner page.
    Uses rear camera to scan member codes.
    """
    business = get_active_business(request)

    return render(
        request,
        "inventory/gym/scan_member.html",
        {
            "active_tab": "scan",
            "business": business,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def gym_leaderboard(request):
    """
    Display gym leaderboard showing top attendees by check-ins.
    Supports period filtering: week, month, all-time.
    """
    business = get_active_business(request)
    today = timezone.now().date()

    # Period filtering
    period = request.GET.get("period", "month")

    if period == "week":
        start_date = today - timedelta(days=7)
        period_label = "This Week"
    elif period == "month":
        start_date = today - timedelta(days=30)
        period_label = "This Month"
    else:  # all
        start_date = None
        period_label = "All Time"

    # Get all active members
    members = GymMember.objects.filter(business=business, is_active=True, is_archived=False)

    # Build leaderboard data
    leaderboard_data = []
    for member in members:
        # Count check-ins in period
        checkins_query = GymCheckIn.objects.filter(business=business, member=member)
        if start_date:
            start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            checkins_query = checkins_query.filter(timestamp__gte=start_dt)

        checkin_count = checkins_query.count()

        if checkin_count > 0:  # Only include members with check-ins
            leaderboard_data.append(
                {
                    "member": member,
                    "checkins": checkin_count,
                }
            )

    # Sort by check-ins (descending)
    leaderboard_data.sort(key=lambda x: x["checkins"], reverse=True)

    # Add rank
    for idx, entry in enumerate(leaderboard_data, start=1):
        entry["rank"] = idx

    # Limit to top 50
    leaderboard_data = leaderboard_data[:50]

    return render(
        request,
        "inventory/gym/leaderboard.html",
        {
            "business": business,
            "leaderboard": leaderboard_data,
            "period": period,
            "period_label": period_label,
        },
    )


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def gym_scan_lookup(request):
    """
    API endpoint to lookup member by scanned code.
    Returns member details, status, days remaining, etc.
    """
    from django.http import JsonResponse

    business = get_active_business(request)

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    # Get scanned code from request
    import json

    try:
        body = json.loads(request.body)
        member_code = body.get("code", "").strip()
    except (json.JSONDecodeError, ValueError):
        member_code = request.POST.get("code", "").strip()

    if not member_code:
        return JsonResponse({"ok": False, "error": "No code provided"}, status=400)

    # Lookup member by code (tenant-safe)
    # Try qr_token first (preferred), then fall back to member_code for legacy support
    try:
        member = GymMember.objects.get(business=business, qr_token=member_code, is_archived=False)
    except GymMember.DoesNotExist:
        try:
            member = GymMember.objects.get(business=business, member_code=member_code, is_archived=False)
        except GymMember.DoesNotExist:
            return JsonResponse(
                {"ok": False, "error": f"Member not found: {member_code}", "code": member_code}, status=404
            )

    # Calculate status and days remaining
    today = timezone.now().date()
    days_left = member.days_left
    is_overdue = False
    is_active = False

    if member.membership_end:
        if member.membership_end >= today:
            is_active = True
        else:
            is_overdue = True
    else:
        is_overdue = True  # No membership at all

    # Determine status color
    if is_active:
        status_color = "success"  # Green
        status_label = "Active"
    elif is_overdue:
        status_color = "danger"  # Red
        status_label = "Expired"
    else:
        status_color = "warning"  # Yellow
        status_label = "Pending Payment"

    # Build response
    return JsonResponse(
        {
            "ok": True,
            "member": {
                "id": member.id,
                "name": member.name,
                "phone": member.phone,
                "email": member.email,
                "member_code": member.member_code,
                "trainer": member.trainer.name if member.trainer else None,
                "days_left": days_left,
                "membership_start": member.membership_start.isoformat() if member.membership_start else None,
                "membership_end": member.membership_end.isoformat() if member.membership_end else None,
                "last_payment_date": member.last_payment_date.isoformat() if member.last_payment_date else None,
                "status": member.status,
                "status_label": status_label,
                "status_color": status_color,
                "is_active": is_active,
                "is_overdue": is_overdue,
                "membership_fee": float(member.membership_fee) if member.membership_fee else 0,
                "trainer_fee": float(member.trainer_fee) if member.trainer_fee else 0,
            },
        }
    )
