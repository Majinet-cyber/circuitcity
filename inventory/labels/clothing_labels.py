# inventory/labels/clothing_labels.py
"""
Label and QR code generation for CLOTHING vertical.
Generates printable product tags with SKU, QR code, and pricing.
"""
from __future__ import annotations

from typing import Optional, BinaryIO
from decimal import Decimal
from io import BytesIO

try:
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import mm, inch
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.graphics.barcode import qr
    from reportlab.graphics import renderPDF

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

from inventory.clothing_config import sign_product_qr_data


# ============================================================================
# LABEL TEMPLATES
# ============================================================================


class LabelSize:
    """Standard label sizes (width x height in mm)"""

    SMALL = (50, 30)  # Small price tag
    MEDIUM = (70, 40)  # Standard product tag
    LARGE = (100, 60)  # Shelf label with large QR
    CUSTOM = None  # Custom size


def generate_label_pdf(
    product,
    variant=None,
    *,
    quantity: int = 1,
    show_price: bool = True,
    label_size: str = "medium",
    output: Optional[BinaryIO] = None,
) -> BytesIO:
    """
    Generate a PDF with product labels.

    Args:
        product: MerchProduct instance
        variant: ClothingVariant instance (optional)
        quantity: Number of labels to generate
        show_price: Whether to show price on label
        label_size: "small", "medium", or "large"
        output: Optional output stream (if None, creates BytesIO)

    Returns:
        BytesIO with PDF data
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError("ReportLab is required for label generation. Install with: pip install reportlab")

    # Create output buffer
    if output is None:
        output = BytesIO()

    # Get label dimensions
    if label_size == "small":
        label_width, label_height = LabelSize.SMALL
    elif label_size == "large":
        label_width, label_height = LabelSize.LARGE
    else:
        label_width, label_height = LabelSize.MEDIUM

    # Convert mm to points (1mm = 2.834645669 points)
    label_width_pt = label_width * mm
    label_height_pt = label_height * mm

    # Calculate grid layout on A4 page
    page_width, page_height = A4
    margin = 10 * mm

    cols = int((page_width - 2 * margin) / label_width_pt)
    rows = int((page_height - 2 * margin) / label_height_pt)

    labels_per_page = cols * rows

    # Create PDF canvas
    c = canvas.Canvas(output, pagesize=A4)

    # Generate labels
    labels_drawn = 0
    page_num = 1

    for i in range(quantity):
        # Calculate position on grid
        col = (labels_drawn % labels_per_page) % cols
        row = (labels_drawn % labels_per_page) // cols

        x = margin + col * label_width_pt
        y = page_height - margin - (row + 1) * label_height_pt

        # Draw single label
        _draw_single_label(
            c,
            product,
            variant,
            x=x,
            y=y,
            width=label_width_pt,
            height=label_height_pt,
            show_price=show_price,
            label_size=label_size,
        )

        labels_drawn += 1

        # New page if needed
        if labels_drawn % labels_per_page == 0 and i < quantity - 1:
            c.showPage()
            page_num += 1

    # Save PDF
    c.save()

    # Reset buffer position
    output.seek(0)

    return output


def _draw_single_label(
    c: canvas.Canvas,
    product,
    variant,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    show_price: bool,
    label_size: str,
):
    """
    Draw a single label on the canvas.

    Args:
        c: ReportLab canvas
        product: MerchProduct instance
        variant: ClothingVariant instance (optional)
        x, y: Position (bottom-left corner)
        width, height: Label dimensions
        show_price: Whether to show price
        label_size: "small", "medium", or "large"
    """
    # Draw border (optional, for debugging)
    # c.setStrokeColor(colors.lightgrey)
    # c.rect(x, y, width, height)

    # Padding
    padding = 2 * mm
    content_x = x + padding
    content_y = y + padding
    content_width = width - 2 * padding
    content_height = height - 2 * padding

    # Get product details
    business = product.business
    product_name = product.name
    brand = getattr(product, "brand", "") or ""
    internal_sku = getattr(product, "internal_sku", "") or product.sku or ""

    if variant:
        variant_sku = variant.variant_sku
        selling_price = variant.get_selling_price()
        size = variant.size
        color = variant.color
    else:
        variant_sku = internal_sku
        selling_price = product.selling_price or Decimal("0.00")
        size = getattr(product, "size", "") or ""
        color = getattr(product, "color", "") or ""

    # Generate QR code data
    qr_token = sign_product_qr_data(
        business_id=business.id,
        product_id=product.id,
        variant_id=variant.id if variant else None,
    )

    # QR code URL (points to scan endpoint)
    from django.conf import settings

    base_url = getattr(settings, "SITE_URL", "https://emajinet.com")
    qr_url = f"{base_url}/inventory/clothing/scan/{qr_token}/"

    # Layout based on label size
    if label_size == "small":
        _draw_small_label(
            c,
            content_x,
            content_y,
            content_width,
            content_height,
            product_name,
            variant_sku,
            selling_price,
            qr_url,
            show_price,
        )
    elif label_size == "large":
        _draw_large_label(
            c,
            content_x,
            content_y,
            content_width,
            content_height,
            business,
            product_name,
            brand,
            variant_sku,
            selling_price,
            size,
            color,
            qr_url,
            show_price,
        )
    else:
        _draw_medium_label(
            c,
            content_x,
            content_y,
            content_width,
            content_height,
            business,
            product_name,
            brand,
            variant_sku,
            selling_price,
            size,
            color,
            qr_url,
            show_price,
        )


def _draw_small_label(c, x, y, width, height, name, sku, price, qr_url, show_price):
    """Draw small label (price tag style)"""
    # QR code (small, right side)
    qr_size = min(height * 0.8, width * 0.3)
    qr_x = x + width - qr_size
    qr_y = y + (height - qr_size) / 2

    qr_code = qr.QrCodeWidget(qr_url)
    bounds = qr_code.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    qr_drawing = qr.Drawing(qr_size, qr_size, transform=[qr_size / qr_width, 0, 0, qr_size / qr_height, 0, 0])
    qr_drawing.add(qr_code)
    renderPDF.draw(qr_drawing, c, qr_x, qr_y)

    # Text (left side)
    text_width = width - qr_size - 2 * mm
    text_x = x

    # Product name (truncated)
    c.setFont("Helvetica-Bold", 8)
    name_short = name[:20] + "..." if len(name) > 20 else name
    c.drawString(text_x, y + height - 8, name_short)

    # SKU
    c.setFont("Helvetica", 6)
    c.drawString(text_x, y + height - 14, f"SKU: {sku}")

    # Price (if enabled)
    if show_price:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(text_x, y + 4, f"K {price:,.2f}")


def _draw_medium_label(c, x, y, width, height, business, name, brand, sku, price, size, color, qr_url, show_price):
    """Draw medium label (standard product tag)"""
    # QR code (right side)
    qr_size = min(height * 0.7, width * 0.35)
    qr_x = x + width - qr_size
    qr_y = y + (height - qr_size) / 2

    qr_code = qr.QrCodeWidget(qr_url)
    bounds = qr_code.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    qr_drawing = qr.Drawing(qr_size, qr_size, transform=[qr_size / qr_width, 0, 0, qr_size / qr_height, 0, 0])
    qr_drawing.add(qr_code)
    renderPDF.draw(qr_drawing, c, qr_x, qr_y)

    # Text (left side)
    text_width = width - qr_size - 3 * mm
    text_x = x
    cursor_y = y + height - 6

    # Business name (small, top)
    c.setFont("Helvetica", 6)
    business_name = business.name[:30]
    c.drawString(text_x, cursor_y, business_name)
    cursor_y -= 8

    # Brand (if present)
    if brand:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(text_x, cursor_y, brand[:20])
        cursor_y -= 8

    # Product name
    c.setFont("Helvetica-Bold", 9)
    name_short = name[:25] + "..." if len(name) > 25 else name
    c.drawString(text_x, cursor_y, name_short)
    cursor_y -= 8

    # Size/Color (if present)
    if size or color:
        c.setFont("Helvetica", 7)
        variant_text = " / ".join(filter(None, [size, color]))
        c.drawString(text_x, cursor_y, variant_text)
        cursor_y -= 7

    # SKU
    c.setFont("Helvetica", 6)
    c.drawString(text_x, cursor_y, f"SKU: {sku}")
    cursor_y -= 8

    # Price (if enabled)
    if show_price:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(text_x, y + 3, f"K {price:,.2f}")


def _draw_large_label(c, x, y, width, height, business, name, brand, sku, price, size, color, qr_url, show_price):
    """Draw large label (shelf label with prominent QR)"""
    # QR code (center-right, larger)
    qr_size = min(height * 0.8, width * 0.4)
    qr_x = x + width - qr_size - 2 * mm
    qr_y = y + (height - qr_size) / 2

    qr_code = qr.QrCodeWidget(qr_url)
    bounds = qr_code.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    qr_drawing = qr.Drawing(qr_size, qr_size, transform=[qr_size / qr_width, 0, 0, qr_size / qr_height, 0, 0])
    qr_drawing.add(qr_code)
    renderPDF.draw(qr_drawing, c, qr_x, qr_y)

    # Text (left side, more spacious)
    text_width = width - qr_size - 5 * mm
    text_x = x + 1 * mm
    cursor_y = y + height - 8

    # Business name
    c.setFont("Helvetica", 7)
    business_name = business.name[:35]
    c.drawString(text_x, cursor_y, business_name)
    cursor_y -= 10

    # Brand (if present)
    if brand:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(text_x, cursor_y, brand[:25])
        cursor_y -= 10

    # Product name (larger font)
    c.setFont("Helvetica-Bold", 11)
    name_short = name[:30] + "..." if len(name) > 30 else name
    c.drawString(text_x, cursor_y, name_short)
    cursor_y -= 10

    # Size/Color (if present)
    if size or color:
        c.setFont("Helvetica", 8)
        variant_text = " / ".join(filter(None, [size, color]))
        c.drawString(text_x, cursor_y, variant_text)
        cursor_y -= 9

    # SKU
    c.setFont("Helvetica", 7)
    c.drawString(text_x, cursor_y, f"SKU: {sku}")
    cursor_y -= 10

    # Price (if enabled, prominent)
    if show_price:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(text_x, y + 5, f"K {price:,.2f}")


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def generate_product_labels(
    product,
    quantity: int = 1,
    show_price: bool = True,
    label_size: str = "medium",
) -> BytesIO:
    """
    Generate labels for a simple product (no variants).

    Returns:
        BytesIO with PDF data
    """
    return generate_label_pdf(
        product=product,
        variant=None,
        quantity=quantity,
        show_price=show_price,
        label_size=label_size,
    )


def generate_variant_labels(
    variant,
    quantity: int = 1,
    show_price: bool = True,
    label_size: str = "medium",
) -> BytesIO:
    """
    Generate labels for a product variant.

    Returns:
        BytesIO with PDF data
    """
    return generate_label_pdf(
        product=variant.product,
        variant=variant,
        quantity=quantity,
        show_price=show_price,
        label_size=label_size,
    )


__all__ = [
    "generate_label_pdf",
    "generate_product_labels",
    "generate_variant_labels",
    "LabelSize",
]
