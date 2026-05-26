from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import underwriter_required
from applications.models import FinancingApplication
from commissions.models import Commission
from commissions.services import cancel_application_commissions, process_application_approval


MAX_ACTIVE = 5


@underwriter_required
def underwriter_dashboard(request):
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
    underwriter_earnings = (
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
        "underwriter_earnings": underwriter_earnings,
    })


@underwriter_required(sensitive=True)
def claim_next(request):
    active_count = FinancingApplication.objects.filter(
        claimed_by=request.user,
        status="under_review",
    ).count()

    if active_count >= MAX_ACTIVE:
        messages.error(request, "You can only have 5 active applications.")
        return redirect("underwriter_dashboard")

    with transaction.atomic():
        app = (
            FinancingApplication.objects.select_for_update()
            .filter(status="pending_review", claimed_by__isnull=True)
            .order_by("submitted_at", "id")
            .first()
        )

        if not app:
            messages.info(request, "No apps pending.")
            return redirect("underwriter_dashboard")

        app.claimed_by = request.user
        app.claimed_at = timezone.now()
        app.status = "under_review"
        app.save(update_fields=["claimed_by", "claimed_at", "status"])

    return redirect("underwriter_review_application", app_id=app.id)


@underwriter_required(sensitive=True)
def review_application(request, app_id):
    app = get_object_or_404(FinancingApplication.objects.select_related("deal", "claimed_by"), id=app_id)
    if app.claimed_by_id and app.claimed_by_id != request.user.id:
        messages.error(request, f"This application is already under review by {app.claimed_by.get_full_name() or app.claimed_by.username}.")
        return redirect("underwriter_dashboard")

    if app.status == "pending_review" and not app.claimed_by_id:
        messages.info(request, "Claim this application before reviewing it.")
        return redirect("underwriter_dashboard")

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
        app.correction_customer_phone_image = "customer_phone_image" in app.correction_fields
        app.reviewed_by = request.user
        app.reviewed_at = timezone.now()

        if decision == "approve":
            app.status = "approved"
            app.correction_fields = []
            app.correction_notes = ""
            messages.success(request, "Application approved.")

        elif decision == "reject":
            if not app.manager_comment.strip():
                messages.error(request, "Underwriter comment is required when rejecting an application.")
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
        return redirect("underwriter_dashboard")

    return render(request, "approvals/review.html", {"app": app, "correction_fields": correction_field_groups()})


@underwriter_required
def active_reviews(request):
    apps = FinancingApplication.objects.filter(claimed_by=request.user, status="under_review").order_by("-claimed_at")
    return render(request, "approvals/list.html", {"title": "My Active Reviews", "apps": apps})


@underwriter_required
def completed_reviews(request):
    statuses = ["approved", "rejected", "correction_requested"]
    if request.GET.get("status") == "rejected":
        statuses = ["rejected"]
    apps = FinancingApplication.objects.filter(
        reviewed_by=request.user,
        status__in=statuses,
    ).order_by("-reviewed_at")
    title = "Rejected Reviews" if request.GET.get("status") == "rejected" else "Completed Reviews"
    return render(request, "approvals/list.html", {"title": title, "apps": apps})


@underwriter_required(sensitive=True)
def address_check(request, app_id):
    app = get_object_or_404(FinancingApplication.objects.select_related("claimed_by"), id=app_id)
    if app.claimed_by_id and app.claimed_by_id != request.user.id:
        messages.error(request, "This application is assigned to another underwriter.")
        return redirect("underwriter_dashboard")

    questions = [
        ("spoke_to_neighbour", "Did you speak to the neighbour?"),
        ("neighbour_confirmed_location", "Did the neighbour confirm the applicant home location?"),
        ("can_locate_if_defaulted", "Would you be able to locate the customer if they defaulted on payment?"),
    ]

    if request.method == "POST":
        app.address_check_answers = {key: request.POST.get(key) == "yes" for key, _label in questions}
        app.save(update_fields=["address_check_answers"])
        messages.success(request, "Address check saved.")
        return redirect("underwriter_review_application", app_id=app.id)

    return render(request, "approvals/address_check.html", {"app": app, "questions": questions})


@underwriter_required(sensitive=True)
def income_check(request, app_id):
    app = get_object_or_404(FinancingApplication.objects.select_related("claimed_by"), id=app_id)
    if app.claimed_by_id and app.claimed_by_id != request.user.id:
        messages.error(request, "This application is assigned to another underwriter.")
        return redirect("underwriter_dashboard")

    questions = [
        ("understands_income", "Do you clearly understand what the applicant does to earn income?"),
        ("spoke_to_proof_contact", "Did you speak to the employer/proof contact?"),
        ("proof_contact_confirmed_work", "Did the employer/proof contact confirm that the customer works for them?"),
        ("proof_contact_confident", "Is the employer/proof contact confident that the customer would pay the monthly amounts?"),
    ]
    income = Decimal(app.exact_monthly_income or app.monthly_income or 0)
    repayment = Decimal(app.calculated_monthly_payment or 0)
    repayment_percent = Decimal("0")
    if income > 0:
        repayment_percent = (repayment / income * Decimal("100")).quantize(Decimal("0.01"))
    affordability = "Affordable"
    if repayment_percent > Decimal("40"):
        affordability = "Risky"
    elif repayment_percent > Decimal("25"):
        affordability = "Caution"

    if request.method == "POST":
        app.income_check_answers = {
            "answers": {key: request.POST.get(key) == "yes" for key, _label in questions},
            "monthly_income": str(income),
            "monthly_repayment": str(repayment),
            "repayment_percent": str(repayment_percent),
            "affordability": affordability,
        }
        app.save(update_fields=["income_check_answers"])
        messages.success(request, "Income check saved.")
        return redirect("underwriter_review_application", app_id=app.id)

    return render(
        request,
        "approvals/income_check.html",
        {
            "app": app,
            "questions": questions,
            "income": income,
            "repayment": repayment,
            "repayment_percent": repayment_percent,
            "affordability": affordability,
        },
    )


@underwriter_required(sensitive=True)
def confirm_approve(request, app_id):
    app = get_object_or_404(FinancingApplication.objects.select_related("claimed_by"), id=app_id)
    if app.claimed_by_id and app.claimed_by_id != request.user.id:
        messages.error(request, "This application is assigned to another underwriter.")
        return redirect("underwriter_dashboard")

    if request.method == "POST":
        app.status = "approved"
        app.reviewed_by = request.user
        app.reviewed_at = timezone.now()
        app.correction_fields = []
        app.correction_notes = ""
        app.save(update_fields=["status", "reviewed_by", "reviewed_at", "correction_fields", "correction_notes"])
        process_application_approval(app, approved_by=request.user)
        messages.success(request, "Application approved.")
        return redirect("underwriter_dashboard")

    return render(request, "approvals/confirm_approve.html", {"app": app})


def legacy_underwriter_dashboard(request):
    return redirect("underwriter_dashboard")


def legacy_claim_next(request):
    return redirect("underwriter_claim_next")


def legacy_review_application(request, app_id):
    return redirect("underwriter_review_application", app_id=app_id)


def correction_field_groups():
    groups = [
        ("Customer", ["customer_name", "national_id", "customer_phone", "occupation", "income_band", "exact_monthly_income"]),
        ("Deal / Pricing", ["selected_deal", "selected_cash_price", "calculated_deposit_amount"]),
        ("KYC Images", ["customer_face_image", "id_front_image", "id_back_image", "customer_phone_image"]),
        (
            "Location + Next of Kin 1",
            [
                "region",
                "district",
                "traditional_authority",
                "precise_location",
                "gps_coordinates",
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
                "proof_income_file",
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
