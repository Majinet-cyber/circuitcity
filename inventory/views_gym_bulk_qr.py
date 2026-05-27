"""
Bulk QR code PDF generation for gym members.
Generates a single PDF with multiple member QR codes in a grid layout for printing as sticker sheets.
"""
from __future__ import annotations

import io
import logging
from datetime import date
from typing import List, Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from core.decorators import manager_required
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from tenants.utils import require_business
from inventory.models_verticals import GymMember

logger = logging.getLogger(__name__)

# Graceful ReportLab imports
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.lib.utils import ImageReader

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not available for bulk PDF generation")

# QR code library
try:
    import qrcode
    from PIL import Image as PILImage

    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logger.warning("qrcode library not available")


# ==============================================================================
# STICKER LAYOUT CONFIGURATION
# ==============================================================================
# These constants define the grid layout for QR stickers on A4 pages.
# Adjust these values to match your sticker sheets or desired layout.
# ==============================================================================

# A4 page dimensions
PAGE_WIDTH, PAGE_HEIGHT = A4  # 210mm x 297mm (595.27pt x 841.89pt)

# Sticker grid configuration
# Option 1: 3 columns x 8 rows = 24 stickers per page (larger stickers ~70x37mm)
# Option 2: 4 columns x 10 rows = 40 stickers per page (smaller stickers ~52x29mm)
STICKERS_PER_ROW = 3
STICKERS_PER_COL = 8

# Margins (distance from page edge to first sticker)
MARGIN_LEFT = 8 * mm
MARGIN_TOP = 10 * mm
MARGIN_RIGHT = 8 * mm
MARGIN_BOTTOM = 10 * mm

# Sticker dimensions (will be auto-calculated to fit grid)
# Calculate available space
AVAILABLE_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
AVAILABLE_HEIGHT = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

# Sticker size with small gap between stickers
STICKER_GAP = 2 * mm  # Gap between stickers
STICKER_WIDTH = (AVAILABLE_WIDTH - (STICKERS_PER_ROW - 1) * STICKER_GAP) / STICKERS_PER_ROW
STICKER_HEIGHT = (AVAILABLE_HEIGHT - (STICKERS_PER_COL - 1) * STICKER_GAP) / STICKERS_PER_COL

# Content padding inside each sticker
PADDING = 2 * mm

# QR code size (square)
QR_SIZE = STICKER_WIDTH - 4 * PADDING  # Leave room for text
if QR_SIZE > STICKER_HEIGHT * 0.6:
    # Ensure QR doesn't dominate sticker height
    QR_SIZE = STICKER_HEIGHT * 0.6

# Font sizes
FONT_NAME_SIZE = 9
FONT_CODE_SIZE = 7
FONT_LOCATION_SIZE = 6


# ==============================================================================
# BULK QR PDF GENERATION
# ==============================================================================


def _generate_qr_image(member: GymMember, request) -> Optional[PILImage.Image]:
    """
    Generate a QR code PIL Image for a member.

    Args:
        member: GymMember instance
        request: HttpRequest for building absolute URLs

    Returns:
        PIL Image object or None if generation fails
    """
    if not QRCODE_AVAILABLE:
        return None

    try:
        # Build public status URL (same as single-member QR)
        status_path = reverse("gym:member_qr_status_public", kwargs={"qr_uuid": str(member.qr_uuid)})
        status_url = request.build_absolute_uri(status_path)

        # Generate QR code with high quality settings for printing
        # Using higher error correction (H) and box_size (12) for crisp printing
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Highest error correction
            box_size=12,  # Higher resolution for crisp printing
            border=2,
        )
        qr.add_data(status_url)
        qr.make(fit=True)

        # Create PIL image (high resolution for printing, must be RGB for ReportLab)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        return qr_img.convert("RGB")
    except Exception as e:
        logger.error(
            f"Failed to generate QR for member {member.id} ({getattr(member, 'name', 'N/A')}), "
            f"qr_uuid={getattr(member, 'qr_uuid', 'N/A')}: {e}",
            exc_info=True
        )
        return None


def _draw_sticker(c: canvas.Canvas, member: GymMember, qr_img: Optional[PILImage.Image], x: float, y: float, request):
    """
    Draw a single QR sticker on the canvas at position (x, y).

    Args:
        c: ReportLab canvas
        member: GymMember instance
        qr_img: PIL QR code image (or None)
        x: X position (bottom-left corner)
        y: Y position (bottom-left corner)
        request: HttpRequest for context
    """
    # Draw sticker border (light gray, for cutting guides)
    c.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
    c.setLineWidth(0.5)
    c.rect(x, y, STICKER_WIDTH, STICKER_HEIGHT, stroke=1, fill=0)

    # Calculate content area
    content_x = x + PADDING
    content_y = y + PADDING
    content_width = STICKER_WIDTH - 2 * PADDING
    content_height = STICKER_HEIGHT - 2 * PADDING

    # Draw QR code (centered horizontally in sticker)
    if qr_img:
        try:
            # Save QR image to bytes for ReportLab
            qr_buffer = io.BytesIO()
            qr_img.save(qr_buffer, format="PNG")
            qr_buffer.seek(0)

            # Wrap BytesIO with ImageReader for ReportLab canvas.drawImage()
            img_reader = ImageReader(qr_buffer)

            # Position QR code (centered horizontally, at top of content area)
            qr_x = x + (STICKER_WIDTH - QR_SIZE) / 2
            qr_y = y + STICKER_HEIGHT - PADDING - QR_SIZE

            # Draw QR image using ImageReader
            c.drawImage(img_reader, qr_x, qr_y, width=QR_SIZE, height=QR_SIZE, preserveAspectRatio=True, mask="auto")
        except Exception as e:
            logger.warning(f"Failed to draw QR image for member {member.id} ({member.name}): {e}", exc_info=True)
            # Draw "QR ERROR" text as fallback
            c.setFont("Helvetica", 6)
            c.setFillColor(colors.red)
            error_text = "QR ERROR"
            error_x = x + (STICKER_WIDTH - stringWidth(error_text, "Helvetica", 6)) / 2
            error_y = y + STICKER_HEIGHT - PADDING - QR_SIZE / 2
            c.drawString(error_x, error_y, error_text)
            c.setFillColor(colors.black)  # Reset color

    # Draw member name (bold, below QR code)
    text_y = y + PADDING + content_height * 0.25
    c.setFont("Helvetica-Bold", FONT_NAME_SIZE)
    c.setFillColor(colors.black)

    # Truncate name if too long
    name = member.name or "Member"
    max_name_width = content_width
    while stringWidth(name, "Helvetica-Bold", FONT_NAME_SIZE) > max_name_width and len(name) > 5:
        name = name[:-1]
    if len(name) < len(member.name or ""):
        name = name.rstrip() + "..."

    # Center name
    name_width = stringWidth(name, "Helvetica-Bold", FONT_NAME_SIZE)
    name_x = x + (STICKER_WIDTH - name_width) / 2
    c.drawString(name_x, text_y, name)

    # Draw member number / code (smaller, below name)
    text_y -= FONT_NAME_SIZE + 2
    c.setFont("Helvetica", FONT_CODE_SIZE)
    member_code = member.member_number or member.member_code or f"ID:{member.id}"
    code_width = stringWidth(member_code, "Helvetica", FONT_CODE_SIZE)
    code_x = x + (STICKER_WIDTH - code_width) / 2
    c.drawString(code_x, text_y, member_code)

    # Optional: Draw gym/location name (very small, at bottom)
    text_y -= FONT_CODE_SIZE + 2
    c.setFont("Helvetica", FONT_LOCATION_SIZE)
    c.setFillColor(colors.Color(0.5, 0.5, 0.5))
    gym_name = member.business.name if member.business else ""
    if gym_name:
        # Truncate gym name
        max_gym_width = content_width
        while stringWidth(gym_name, "Helvetica", FONT_LOCATION_SIZE) > max_gym_width and len(gym_name) > 5:
            gym_name = gym_name[:-1]
        if len(gym_name) < len(member.business.name):
            gym_name = gym_name.rstrip() + "..."
        gym_width = stringWidth(gym_name, "Helvetica", FONT_LOCATION_SIZE)
        gym_x = x + (STICKER_WIDTH - gym_width) / 2
        c.drawString(gym_x, text_y, gym_name)


def _generate_bulk_qr_pdf(members: List[GymMember], request) -> Optional[bytes]:
    """
    Generate a bulk QR PDF for multiple members.

    Args:
        members: List of GymMember instances
        request: HttpRequest for building URLs

    Returns:
        PDF bytes or None if generation fails
    """
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab not available for PDF generation")
        return None

    if not QRCODE_AVAILABLE:
        logger.error("qrcode library not available for QR generation")
        return None

    buffer = io.BytesIO()

    try:
        # Create PDF canvas
        c = canvas.Canvas(buffer, pagesize=A4)

        # Track position in grid
        sticker_count = 0
        total_stickers = len(members)

        for idx, member in enumerate(members):
            # Generate QR image for this member
            qr_img = _generate_qr_image(member, request)

            # Calculate grid position
            row = sticker_count // STICKERS_PER_ROW
            col = sticker_count % STICKERS_PER_ROW

            # Check if we need a new page
            if row >= STICKERS_PER_COL:
                # Start new page
                c.showPage()
                row = 0
                col = 0
                sticker_count = 0

            # Calculate sticker position (origin at bottom-left)
            x = MARGIN_LEFT + col * (STICKER_WIDTH + STICKER_GAP)
            y = PAGE_HEIGHT - MARGIN_TOP - (row + 1) * STICKER_HEIGHT - row * STICKER_GAP

            # Draw sticker
            _draw_sticker(c, member, qr_img, x, y, request)

            sticker_count += 1

        # Save PDF
        c.save()
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(f"Generated bulk QR PDF for {total_stickers} members ({len(pdf_bytes)} bytes)")
        return pdf_bytes

    except Exception as e:
        logger.error(f"Bulk QR PDF generation failed: {e}", exc_info=True)
        buffer.close()
        return None


# ==============================================================================
# VIEW: BULK DOWNLOAD ENDPOINT
# ==============================================================================


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
@require_http_methods(["GET"])
def bulk_qr_pdf(request):
    """
    Generate and download a bulk QR sticker PDF for gym members.

    Query parameters:
    - filter: 'active', 'archived', or '' (all) - same as members list
    - members: comma-separated member IDs (for selected members)
    - all: '1' to download all members matching current filter

    Security: Only managers/admins can bulk download.

    Returns:
        application/pdf response with filename: gym_qr_stickers_<business>_<location>_<date>.pdf
    """
    business = get_active_business(request)

    # Check if ReportLab and qrcode are available
    if not REPORTLAB_AVAILABLE or not QRCODE_AVAILABLE:
        messages.error(
            request,
            "PDF generation is not available. Please contact support. "
            "(Missing libraries: ReportLab or qrcode)",
        )
        # Return a plain text error response (fallback)
        return HttpResponse(
            "PDF generation is not available. Please install required libraries: "
            "pip install reportlab 'qrcode[pil]'",
            status=503,
            content_type="text/plain",
        )

    # Determine which members to include
    selected_ids = request.GET.get("members", "").strip()
    filter_type = request.GET.get("filter", "active")
    download_all = request.GET.get("all", "0") == "1"

    members = GymMember.objects.filter(business=business)

    if selected_ids:
        # Option C: Selected members via checkboxes
        try:
            member_ids = [int(mid.strip()) for mid in selected_ids.split(",") if mid.strip()]
            members = members.filter(id__in=member_ids)
        except ValueError:
            return HttpResponse("Invalid member IDs provided.", status=400, content_type="text/plain")
    elif download_all:
        # Option A/B: All members or filtered set
        if filter_type == "active":
            members = members.filter(is_active=True, is_archived=False)
        elif filter_type == "archived":
            members = members.filter(is_archived=True)
        # else: all members (no additional filter)
    else:
        # No selection provided
        messages.error(request, "Please select members to download or use 'Download All'.")
        return HttpResponse("No members selected for download.", status=400, content_type="text/plain")

    # Order by name for consistent output
    members = members.select_related("business").order_by("name")
    members_list = list(members)

    if not members_list:
        return HttpResponse("No members found matching your criteria.", status=404, content_type="text/plain")

    # Performance check: warn if too many members (but still generate)
    if len(members_list) > 1000:
        logger.warning(f"Bulk QR PDF requested for {len(members_list)} members (business={business.id})")

    # Generate PDF
    pdf_bytes = _generate_bulk_qr_pdf(members_list, request)

    if not pdf_bytes:
        messages.error(request, "Failed to generate QR PDF. Please try again or contact support.")
        return HttpResponse(
            "PDF generation failed. Please check server logs or contact support.",
            status=500,
            content_type="text/plain",
        )

    # Build filename
    today_str = date.today().strftime("%Y-%m-%d")
    # Sanitize business name for filename
    business_name = "".join(c for c in business.name if c.isalnum() or c in (" ", "-", "_")).strip()
    business_name = business_name.replace(" ", "_")[:30]  # Limit length
    location_name = ""  # Could add location if multi-location support exists
    if location_name:
        filename = f"gym_qr_stickers_{business_name}_{location_name}_{today_str}.pdf"
    else:
        filename = f"gym_qr_stickers_{business_name}_{today_str}.pdf"

    # Return PDF response
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(pdf_bytes)

    logger.info(f"Bulk QR PDF downloaded: {filename} ({len(members_list)} members)")
    return response

