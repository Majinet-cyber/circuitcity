from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from applications.models import FinancingApplication


MAX_ACTIVE = 5


@login_required
def manager_home(request):
    my_active = FinancingApplication.objects.filter(
        claimed_by=request.user,
        status="under_review",
    )

    pending_count = FinancingApplication.objects.filter(
        status="submitted",
        claimed_by__isnull=True,
    ).count()

    return render(request, "approvals/home.html", {
        "my_active": my_active,
        "pending_count": pending_count,
        "active_count": my_active.count(),
        "max_active": MAX_ACTIVE,
    })


@login_required
def claim_next(request):
    active_count = FinancingApplication.objects.filter(
        claimed_by=request.user,
        status="under_review",
    ).count()

    if active_count >= MAX_ACTIVE:
        messages.error(request, "You can only have 5 active applications.")
        return redirect("manager_home")

    app = FinancingApplication.objects.filter(
        status="submitted",
        claimed_by__isnull=True,
    ).order_by("submitted_at").first()

    if not app:
        messages.info(request, "No apps pending.")
        return redirect("manager_home")

    app.claimed_by = request.user
    app.claimed_at = timezone.now()
    app.status = "under_review"
    app.save()

    return redirect("review_application", app_id=app.id)


@login_required
def review_application(request, app_id):
    app = get_object_or_404(FinancingApplication, id=app_id, claimed_by=request.user)

    if request.method == "POST":
        decision = request.POST.get("decision")
        app.manager_comment = request.POST.get("manager_comment", "")
        app.correction_notes = request.POST.get("correction_notes", "")
        app.correction_customer_face_image = bool(request.POST.get("correction_customer_face_image"))
        app.correction_id_front_image = bool(request.POST.get("correction_id_front_image"))
        app.correction_id_back_image = bool(request.POST.get("correction_id_back_image"))
        app.reviewed_at = timezone.now()

        if decision == "approve":
            app.status = "approved"
            messages.success(request, "Application approved.")

        elif decision == "reject":
            app.status = "rejected"
            messages.warning(request, "Application rejected.")

        elif decision == "request_correction":
            app.status = "correction_requested"
            messages.info(request, "Correction requested.")

        app.save()
        return redirect("manager_home")

    return render(request, "approvals/review.html", {"app": app})
