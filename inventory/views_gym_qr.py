"""
QR code views for gym members - public status pages and QR image generation.
"""
from __future__ import annotations

import io
import uuid
from io import BytesIO
from typing import Optional

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_http_methods

from inventory.models_verticals import GymMember
from inventory.services.gym_status import get_member_status

# Graceful ReportLab imports
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _get_qrcode_module():
    """
    Lazy import helper for qrcode module.
    Raises ImportError with helpful message if qrcode is not installed.
    """
    try:
        import qrcode

        return qrcode
    except ImportError:
        raise ImportError("qrcode module is not installed. Please install it with: pip install 'qrcode[pil]'")


@require_http_methods(["GET"])
def member_qr_status_public(request, qr_uuid: str):
    """
    Public member status page accessible via QR code scan.
    No authentication required.

    Shows:
    - Member Name
    - Gym Number (member_number)
    - Status: Active or Overdue
    - Next Payment date
    - Link to full member profile (redirects to login if not authenticated)
    """
    try:
        # Validate UUID format (though URL routing should handle this)
        uuid.UUID(str(qr_uuid))
        member = get_object_or_404(GymMember, qr_uuid=qr_uuid, is_archived=False)
    except (ValueError, TypeError, AttributeError):
        # Invalid UUID format
        raise Http404("Member not found")

    # Get member status
    status_info = get_member_status(member)

    # Build URL for full member profile
    if request.user.is_authenticated:
        # If logged in and has access to this business, show direct link
        from inventory.authz import get_active_business

        try:
            business = get_active_business(request)
            if business and business.id == member.business_id:
                full_profile_url = reverse("gym:member_detail", args=[member.id])
            else:
                full_profile_url = None
        except Exception:
            full_profile_url = None
    else:
        full_profile_url = None

    # If no direct link, show login redirect with return URL
    if not full_profile_url:
        login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
        # Add next parameter to redirect back to member detail after login
        from urllib.parse import urlencode

        return_url = request.build_absolute_uri(reverse("gym:member_detail", args=[member.id]))
        full_profile_url = f"{login_url}?{urlencode({'next': return_url})}"

    context = {
        "member": member,
        "status": status_info["status"],
        "next_payment_date": status_info["next_payment_date"],
        "reason": status_info["reason"],
        "full_profile_url": full_profile_url,
        "is_authenticated": request.user.is_authenticated,
    }

    return render(request, "inventory/gym/qr_status_public.html", context)


@require_http_methods(["GET"])
@cache_control(no_store=True)
def public_member_status(request, token: str):
    """
    Public member status page accessible via short token link.
    No authentication required. Read-only.

    URL: /gym/m/<token>/

    Shows:
    - Member name (optional display)
    - Gym name
    - Membership status: Active / Expired / Suspended
    - Valid from / valid to (next due date)
    - Last check-in time (optional)

    Template includes noindex meta tag for SEO exclusion.
    """
    member = get_object_or_404(GymMember, public_token=token, is_archived=False)

    # Get member status
    status_info = get_member_status(member)

    # Map status to human-readable label
    status_code = status_info.get("status", "UNKNOWN").upper()
    status_labels = {
        "ACTIVE": "Active",
        "EXPIRED": "Expired",
        "OVERDUE": "Expired",  # Treat overdue as expired for simplicity
        "SUSPENDED": "Suspended",
        "PENDING": "Pending Payment",
        "PENDING_PAYMENT": "Pending Payment",
    }
    status_label = status_labels.get(status_code, status_code.title())

    # Build context
    context = {
        "member": member,
        "gym_name": member.business.name if member.business else "Gym",
        "status_code": status_code,
        "status_label": status_label,
        "next_payment_date": status_info.get("next_payment_date"),
        "membership_start": member.membership_start,
        "membership_end": member.membership_end,
        "last_checkin_date": member.last_checkin_date,
        "reason": status_info.get("reason", ""),
    }

    return render(request, "inventory/gym/public_member_status.html", context)


@require_http_methods(["GET"])
def member_qr_png(request, qr_uuid):
    """
    Generate QR code PNG image for a member.
    Ultra-strict implementation that NEVER returns HTML - only PNG bytes.
    """
    try:
        import qrcode
    except ImportError:
        raise Http404("QR lib missing. pip install 'qrcode[pil]'")

    member = get_object_or_404(GymMember, qr_uuid=qr_uuid)

    # IMPORTANT: build absolute public status URL
    status_path = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": member.qr_uuid})
    status_url = request.build_absolute_uri(status_path)

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=3,
    )
    qr.add_data(status_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    buf = BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    resp = HttpResponse(data, content_type="image/png")
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


@require_http_methods(["GET"])
def member_qr_print(request, qr_uuid: str):
    """
    Print-friendly page with large QR code, member name, and gym number.
    """
    try:
        uuid.UUID(str(qr_uuid))
        member = get_object_or_404(GymMember, qr_uuid=qr_uuid, is_archived=False)
    except (ValueError, TypeError, AttributeError):
        raise Http404("Member not found")

    # Get QR image URL
    qr_image_url = request.build_absolute_uri(reverse("gym:member_qr_png", args=[str(member.qr_uuid)]))

    context = {
        "member": member,
        "qr_image_url": qr_image_url,
    }

    return render(request, "inventory/gym/qr_print.html", context)


def _generate_member_card_pdf(member: GymMember, request) -> Optional[bytes]:
    """
    Generate PDF member card with QR code for a gym member.

    Args:
        member: GymMember instance
        request: HttpRequest for building absolute URLs

    Returns:
        PDF bytes or None if ReportLab not available
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not REPORTLAB_AVAILABLE:
        logger.warning("ReportLab not available for PDF generation")
        return None

    # Create PDF buffer
    buffer = io.BytesIO()

    try:
        # Create PDF document (letter size, landscape orientation would be better but letter is fine)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        # Build PDF content
        story = []
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "CardTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=20,
            alignment=TA_CENTER,
        )

        heading_style = ParagraphStyle(
            "CardHeading",
            parent=styles["Heading2"],
            fontSize=16,
            textColor=colors.HexColor("#333333"),
            spaceAfter=10,
            alignment=TA_CENTER,
        )

        normal_style = ParagraphStyle(
            "CardNormal",
            parent=styles["Normal"],
            fontSize=12,
            textColor=colors.HexColor("#333333"),
            alignment=TA_CENTER,
        )

        # Get member status
        status_info = get_member_status(member)
        status_label = status_info.get("status", "UNKNOWN").upper()
        next_payment = status_info.get("next_payment_date")

        # Title
        story.append(Paragraph("<b>Gym Member Card</b>", title_style))
        story.append(Spacer(1, 0.5 * cm))

        # Member Name (fallback if missing)
        member_name = getattr(member, 'name', 'Member') or 'Member'
        story.append(Paragraph(f"<b>{member_name}</b>", heading_style))

        # Gym Number
        gym_number = member.member_number or member.member_code or "N/A"
        story.append(Paragraph(f"Gym #: {gym_number}", normal_style))
        story.append(Spacer(1, 0.5 * cm))

        # QR Code Image (centered)
        try:
            qrcode_module = _get_qrcode_module()
            public_url = request.build_absolute_uri(reverse("gym:member_qr_status_public", args=[str(member.qr_uuid)]))

            # Generate QR code image
            qr = qrcode_module.QRCode(
                version=1,
                error_correction=qrcode_module.constants.ERROR_CORRECT_M,
                box_size=12,
                border=3,
            )
            qr.add_data(public_url)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")

            # Convert QR to bytes for ReportLab Image
            qr_buffer = BytesIO()
            qr_img.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)

            # Add QR code image (5cm x 5cm, centered)
            qr_image = Image(qr_buffer, width=5 * cm, height=5 * cm)
            qr_image.hAlign = "CENTER"
            story.append(qr_image)
            story.append(Spacer(1, 0.5 * cm))
        except Exception as e:
            # If QR generation fails, add fallback text
            logger.warning(f"QR code generation failed for member {member.id}: {e}")
            story.append(Paragraph("QR Code generation failed", normal_style))
            story.append(Spacer(1, 0.5 * cm))

        # Status
        status_color = "#16a34a" if status_label == "ACTIVE" else "#dc2626"
        story.append(Paragraph(f'<b>Status: <font color="{status_color}">{status_label}</font></b>', normal_style))

        # Next Payment Date
        if next_payment:
            story.append(Paragraph(f"Next Payment: {next_payment.strftime('%B %d, %Y')}", normal_style))

        story.append(Spacer(1, 1 * cm))

        # Footer note
        footer_style = ParagraphStyle(
            "CardFooter",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#666666"),
            alignment=TA_CENTER,
        )
        story.append(Paragraph("Scan QR code to view member status online", footer_style))

        # Build PDF
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
    except Exception as e:
        logger.error(f"PDF generation failed for member {member.id}: {e}", exc_info=True)
        buffer.close()
        return None


@require_http_methods(["GET"])
def member_qr_card_pdf(request, qr_uuid: str):
    """
    Generate and return PDF member card with QR code.
    Returns application/pdf response.
    """
    try:
        uuid.UUID(str(qr_uuid))
        member = get_object_or_404(GymMember, qr_uuid=qr_uuid, is_archived=False)
    except (ValueError, TypeError, AttributeError):
        raise Http404("Member not found")

    # Generate PDF
    pdf_bytes = _generate_member_card_pdf(member, request)

    if not pdf_bytes:
        # ReportLab not available or error occurred
        return HttpResponse(
            "PDF generation is not available. Please contact support.", status=503, content_type="text/plain"
        )

    # Return PDF response
    filename = f"Gym-QR-{member.member_number or member.id}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
