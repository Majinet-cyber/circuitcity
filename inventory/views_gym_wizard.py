# inventory/views_gym_wizard.py
"""
Gamified wizard flow for adding gym members.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models_verticals import (
    GymMember,
    GymSettings,
    GymTrainer,
    GymMemberLog,
    GymMemberAction,
    GymMemberStatus,
)
from tenants.utils import require_business


# Session keys
WIZARD_SESSION_KEY = "gym_member_wizard"


def _get_wizard_data(request):
    """Get wizard data from session"""
    return request.session.get(WIZARD_SESSION_KEY, {})


def _set_wizard_data(request, data):
    """Store wizard data in session"""
    request.session[WIZARD_SESSION_KEY] = data
    request.session.modified = True


def _clear_wizard_data(request):
    """Clear wizard data from session"""
    if WIZARD_SESSION_KEY in request.session:
        del request.session[WIZARD_SESSION_KEY]
        request.session.modified = True


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def member_add_wizard(request):
    """
    Multi-step gamified wizard for adding gym members.

    Steps:
    0 - Welcome screen
    1 - Name + Phone
    2 - Trainer selection (optional)
    3 - Confirm summary
    4 - Success + QR code
    """
    business = get_active_business(request)
    step = int(request.GET.get("step", 0))

    # Get gym settings for fees
    try:
        gym_settings = GymSettings.objects.get(business=business)
    except GymSettings.DoesNotExist:
        gym_settings = GymSettings.objects.create(business=business)

    # Route to step handlers
    if step == 0:
        return _wizard_step_welcome(request, business, gym_settings)
    elif step == 1:
        return _wizard_step_details(request, business, gym_settings)
    elif step == 2:
        return _wizard_step_trainer(request, business, gym_settings)
    elif step == 3:
        return _wizard_step_confirm(request, business, gym_settings)
    elif step == 4:
        return _wizard_step_success(request, business, gym_settings)
    else:
        _clear_wizard_data(request)
        return redirect(f"{request.path}?step=0")


def _wizard_step_welcome(request, business, gym_settings):
    """Step 0: Welcome screen"""
    if request.method == "POST":
        _clear_wizard_data(request)  # Start fresh
        return redirect(f"{request.path}?step=1")

    return render(
        request,
        "inventory/gym/wizard/step_welcome.html",
        {
            "business": business,
            "gym_settings": gym_settings,
            "step": 0,
            "total_steps": 3,
        },
    )


def _wizard_step_details(request, business, gym_settings):
    """Step 1: Name + Phone"""
    wizard_data = _get_wizard_data(request)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip()

        # Validation
        errors = []
        if not name:
            errors.append("Name is required")
        if not phone:
            errors.append("Phone number is required")

        # Check for duplicate phone
        if phone and GymMember.objects.filter(business=business, phone=phone, is_archived=False).exists():
            errors.append(f"A member with phone {phone} already exists")

        if errors:
            return render(
                request,
                "inventory/gym/wizard/step_details.html",
                {
                    "business": business,
                    "gym_settings": gym_settings,
                    "step": 1,
                    "total_steps": 3,
                    "errors": errors,
                    "name": name,
                    "phone": phone,
                    "email": email,
                },
            )

        # Save to session
        wizard_data["name"] = name
        wizard_data["phone"] = phone
        wizard_data["email"] = email
        _set_wizard_data(request, wizard_data)

        return redirect(f"{request.path}?step=2")

    return render(
        request,
        "inventory/gym/wizard/step_details.html",
        {
            "business": business,
            "gym_settings": gym_settings,
            "step": 1,
            "total_steps": 3,
            "name": wizard_data.get("name", ""),
            "phone": wizard_data.get("phone", ""),
            "email": wizard_data.get("email", ""),
        },
    )


def _wizard_step_trainer(request, business, gym_settings):
    """Step 2: Trainer selection (optional)"""
    wizard_data = _get_wizard_data(request)

    # Check if previous step completed
    if not wizard_data.get("name"):
        return redirect(f"{request.path}?step=1")

    trainers = GymTrainer.objects.filter(business=business, is_active=True).order_by("name")

    if request.method == "POST":
        trainer_id = request.POST.get("trainer_id", "")

        if trainer_id and trainer_id != "none":
            try:
                trainer = GymTrainer.objects.get(id=trainer_id, business=business, is_active=True)
                wizard_data["trainer_id"] = trainer.id
                wizard_data["trainer_name"] = trainer.name
            except GymTrainer.DoesNotExist:
                wizard_data["trainer_id"] = None
                wizard_data["trainer_name"] = None
        else:
            wizard_data["trainer_id"] = None
            wizard_data["trainer_name"] = None

        _set_wizard_data(request, wizard_data)
        return redirect(f"{request.path}?step=3")

    return render(
        request,
        "inventory/gym/wizard/step_trainer.html",
        {
            "business": business,
            "gym_settings": gym_settings,
            "step": 2,
            "total_steps": 3,
            "trainers": trainers,
            "selected_trainer_id": wizard_data.get("trainer_id"),
        },
    )


def _wizard_step_confirm(request, business, gym_settings):
    """Step 3: Confirm and create member"""
    wizard_data = _get_wizard_data(request)

    # Check if previous steps completed
    if not wizard_data.get("name") or not wizard_data.get("phone"):
        return redirect(f"{request.path}?step=1")

    if request.method == "POST":
        mark_as_paid = request.POST.get("mark_as_paid") == "yes"

        # Create member
        with transaction.atomic():
            member = GymMember(
                business=business,
                name=wizard_data["name"],
                phone=wizard_data["phone"],
                email=wizard_data.get("email", ""),
                membership_fee=gym_settings.default_membership_price,
            )

            # Set trainer if selected
            if wizard_data.get("trainer_id"):
                try:
                    trainer = GymTrainer.objects.get(id=wizard_data["trainer_id"], business=business)
                    member.trainer = trainer
                    member.has_trainer = True
                    member.trainer_fee = gym_settings.default_trainer_fee
                except GymTrainer.DoesNotExist:
                    pass

            member.save()

            # Activate membership if paid
            if mark_as_paid:
                member.set_paid(
                    payment_date=timezone.now().date(),
                    membership_fee=member.membership_fee,
                    trainer_fee=member.trainer_fee if member.has_trainer else None,
                    paid_by=request.user,
                )
                messages.success(
                    request,
                    f"Member '{member.name}' added and activated! Membership valid until {member.membership_end.strftime('%d %b %Y')}.",
                )
            else:
                member.status = GymMemberStatus.PENDING_PAYMENT
                member.save(update_fields=["status"])
                messages.success(request, f"Member '{member.name}' added successfully. Remember to collect payment.")

            # Log creation
            GymMemberLog.objects.create(
                member=member,
                action=GymMemberAction.CREATED,
                changes={
                    "name": member.name,
                    "phone": member.phone,
                    "trainer": member.trainer.name if member.trainer else None,
                    "marked_as_paid": mark_as_paid,
                },
                performed_by=request.user,
            )

            # Store member ID in wizard data for success screen
            wizard_data["member_id"] = member.id
            wizard_data["marked_as_paid"] = mark_as_paid
            _set_wizard_data(request, wizard_data)

        return redirect(f"{request.path}?step=4")

    # Calculate total fees
    membership_fee = gym_settings.default_membership_price or 0
    trainer_fee = gym_settings.default_trainer_fee if wizard_data.get("trainer_id") else 0
    total = membership_fee + trainer_fee

    return render(
        request,
        "inventory/gym/wizard/step_confirm.html",
        {
            "business": business,
            "gym_settings": gym_settings,
            "step": 3,
            "total_steps": 3,
            "wizard_data": wizard_data,
            "membership_fee": membership_fee,
            "trainer_fee": trainer_fee,
            "total_fee": total,
        },
    )


def _wizard_step_success(request, business, gym_settings):
    """Step 4: Success screen with QR code"""
    wizard_data = _get_wizard_data(request)

    member_id = wizard_data.get("member_id")
    if not member_id:
        return redirect(f"{request.path}?step=0")

    try:
        member = GymMember.objects.get(id=member_id, business=business)
    except GymMember.DoesNotExist:
        _clear_wizard_data(request)
        return redirect(f"{request.path}?step=0")

    # Clear wizard data after showing success
    if request.method == "POST":
        _clear_wizard_data(request)
        action = request.POST.get("action", "dashboard")
        if action == "add_another":
            return redirect(f"{request.path}?step=0")
        elif action == "view_member":
            return redirect("gym:member_detail", member_id=member.id)
        else:
            return redirect("gym:dashboard")

    return render(
        request,
        "inventory/gym/wizard/step_success.html",
        {
            "business": business,
            "gym_settings": gym_settings,
            "step": 4,
            "total_steps": 3,
            "member": member,
            "marked_as_paid": wizard_data.get("marked_as_paid", False),
        },
    )
