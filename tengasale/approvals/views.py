from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from applications.models import FinancingApplication
from commissions.models import Commission
from commissions.services import cancel_application_commissions, process_application_approval


MAX_ACTIVE = 5


@login_required
def manager_home(request):
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied

    my_active = FinancingApplication.objects.filter(
        claimed_by=request.user,
        status="under_review",
    )

    pending_count = FinancingApplication.objects.filter(
        status="pending_review",
        claimed_by__isnull=True,
    ).count()
    pending_queue = FinancingApplication.objects.select_related("created_by").filter(
        status="pending_review",
        claimed_by__isnull=True,
    ).order_by("submitted_at", "id")[:10]

    completed_reviews = FinancingApplication.objects.filter(
        reviewed_by=request.user,
        status__in=["approved", "rejected", "correction_requested"],
    ).order_by("-reviewed_at")[:10]
    manager_earnings = (
        Commission.objects.filter(user=request.user, role=Commission.ROLE_MANAGER)
        .exclude(status=Commission.STATUS_CANCELLED)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )

    return render(request, "approvals/home.html", {
        "my_active": my_active,
        "pending_count": pending_count,
        "pending_queue": pending_queue,
        "completed_reviews": completed_reviews,
        "active_count": my_active.count(),
        "max_active": MAX_ACTIVE,
        "manager_earnings": manager_earnings,
    })


@login_required
def claim_next(request):
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied

    active_count = FinancingApplication.objects.filter(
        claimed_by=request.user,
        status="under_review",
    ).count()

    if active_count >= MAX_ACTIVE:
        messages.error(request, "You can only have 5 active applications.")
        return redirect("manager_home")

    with transaction.atomic():
        app = (
            FinancingApplication.objects.select_for_update()
            .filter(status="pending_review", claimed_by__isnull=True)
            .order_by("submitted_at", "id")
            .first()
        )

        if not app:
            messages.info(request, "No apps pending.")
            return redirect("manager_home")

        app.claimed_by = request.user
        app.claimed_at = timezone.now()
        app.status = "under_review"
        app.save(update_fields=["claimed_by", "claimed_at", "status"])

    return redirect("review_application", app_id=app.id)


@login_required
def review_application(request, app_id):
    if not request.user.is_staff and not request.user.is_superuser:
        raise PermissionDenied

    app = get_object_or_404(FinancingApplication.objects.select_related("deal", "claimed_by"), id=app_id)
    if app.claimed_by_id and app.claimed_by_id != request.user.id:
        messages.error(request, f"This application is already under review by {app.claimed_by.get_full_name() or app.claimed_by.username}.")
        return redirect("manager_home")

    if app.status == "pending_review" and not app.claimed_by_id:
        messages.info(request, "Claim this application before reviewing it.")
        return redirect("manager_home")

    if request.method == "POST":
        decision = request.POST.get("decision")
        app.manager_comment = request.POST.get("manager_comment", "")
        app.correction_notes = request.POST.get("correction_notes", "")
        selected_fields = request.POST.getlist("correction_fields")
        app.correction_fields = [
            field_name
            for field_name in FinancingApplication.CORRECTION_FIELD_ORDER
            if field_name in selected_fields
        ]
        app.correction_customer_face_image = "customer_face_image" in app.correction_fields
        app.correction_id_front_image = "id_front_image" in app.correction_fields
        app.correction_id_back_image = "id_back_image" in app.correction_fields
        app.reviewed_by = request.user
        app.reviewed_at = timezone.now()

        if decision == "approve":
            app.status = "approved"
            app.correction_fields = []
            app.correction_notes = ""
            messages.success(request, "Application approved.")

        elif decision == "reject":
            if not app.manager_comment.strip():
                messages.error(request, "Manager comment is required when rejecting an application.")
                return render(request, "approvals/review.html", {"app": app, "correction_fields": correction_field_groups()})
            app.status = "rejected"
            cancel_application_commissions(app)
            messages.warning(request, "Application rejected.")

        elif decision == "request_correction":
            if not app.correction_fields:
                messages.error(request, "Select at least one field to send back for correction.")
                return render(request, "approvals/review.html", {"app": app, "correction_fields": correction_field_groups()})
            app.status = "correction_requested"
            messages.info(request, "Correction requested.")

        app.save()
        if decision == "approve":
            process_application_approval(app, approved_by=request.user)
        return redirect("manager_home")

    return render(request, "approvals/review.html", {"app": app, "correction_fields": correction_field_groups()})


def correction_field_groups():
    groups = [
        ("Customer", ["customer_name", "national_id", "customer_phone", "occupation", "income_band", "exact_monthly_income"]),
        ("Deal / Pricing", ["selected_deal", "selected_cash_price", "calculated_deposit_amount"]),
        ("KYC Images", ["customer_face_image", "id_front_image", "id_back_image"]),
        (
            "Location + Next of Kin 1",
            [
                "region",
                "district",
                "traditional_authority",
                "precise_location",
                "map_screenshot",
                "next_of_kin_1_name",
                "next_of_kin_1_phone",
                "next_of_kin_1_relationship",
            ],
        ),
        (
            "Work / Proof + Next of Kin 2",
            [
                "work_description",
                "next_of_kin_2_name",
                "next_of_kin_2_phone",
                "next_of_kin_2_relationship",
                "proof_of_income_type",
                "proof_contact_name",
                "proof_contact_phone",
                "proof_notes",
            ],
        ),
        ("Signature / Terms", ["customer_signature", "agreed_to_terms"]),
    ]
    return [
        (
            section,
            [
                {"name": field_name, "label": FinancingApplication.CORRECTION_FIELD_LABELS[field_name]}
                for field_name in field_names
            ],
        )
        for section, field_names in groups
    ]
