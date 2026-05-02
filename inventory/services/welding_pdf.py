# inventory/services/welding_pdf.py
"""
PDF generation for Welding quotes and invoices.
Uses ReportLab to generate professional, branded documents.

Robustness requirements:
- Must NEVER fail: always return a valid PDF
- Missing logo → fallback to initials
- Missing customer email → still generate
- Missing optional fields → still generate
- Log errors but continue with defaults
"""
from __future__ import annotations

import io
import logging
import os
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Graceful ReportLab imports
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        Image, 
        Paragraph, 
        SimpleDocTemplate, 
        Spacer, 
        Table, 
        TableStyle,
        HRFlowable,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not installed. Quote PDF generation will not work.")


# Brand colors
BRAND_ORANGE = colors.HexColor("#f97316")
BRAND_DARK = colors.HexColor("#0c0a09")
BRAND_GRAY = colors.HexColor("#78716c")
BRAND_LIGHT = colors.HexColor("#fafaf9")


def _safe_str(value, default: str = "") -> str:
    """Safely convert value to string, handling None."""
    if value is None:
        return default
    return str(value).strip() or default


def _safe_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    """Safely convert value to Decimal."""
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _get_initials(name: str) -> str:
    """Get initials from a name (max 2 characters)."""
    if not name:
        return "WS"
    words = name.split()
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return name[:2].upper()


def generate_quote_pdf(quote, business=None) -> Optional[bytes]:
    """
    Generate a professional PDF for a welding quote.
    
    Args:
        quote: WeldingQuote model instance
        business: Optional Business model instance (uses quote.business if not provided)
    
    Returns:
        PDF bytes or None if ReportLab not available
    
    This function is designed to NEVER fail - it handles all missing data gracefully.
    """
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab not installed. Cannot generate quote PDF.")
        return None
    
    try:
        return _generate_quote_pdf_internal(quote, business)
    except Exception as e:
        logger.error(f"Error generating quote PDF: {e}", exc_info=True)
        # Try to generate minimal fallback PDF
        try:
            return _generate_fallback_pdf(quote)
        except Exception as e2:
            logger.error(f"Fallback PDF generation also failed: {e2}", exc_info=True)
            return None


def _generate_quote_pdf_internal(quote, business=None) -> bytes:
    """Internal PDF generation - may raise exceptions."""
    # Get data with safe defaults
    if business is None:
        business = getattr(quote, 'business', None)
    
    # Business info
    business_name = _safe_str(getattr(business, 'name', None), "Welding Workshop")
    business_phone = _safe_str(getattr(business, 'phone', None))
    business_email = _safe_str(getattr(business, 'email', None))
    business_address = _safe_str(getattr(business, 'address', None))
    business_logo = getattr(business, 'logo', None) or getattr(business, 'logo_image', None)
    
    # Quote info
    quote_number = _safe_str(getattr(quote, 'quote_number', None), f"WQ-{timezone.now().strftime('%Y%m%d')}")
    created_at = getattr(quote, 'created_at', None) or timezone.now()
    valid_until = getattr(quote, 'valid_until', None)
    
    # Customer info
    customer_name = _safe_str(getattr(quote, 'customer_name', None), "Customer")
    customer_phone = _safe_str(getattr(quote, 'customer_phone', None))
    customer_email = _safe_str(getattr(quote, 'customer_email', None))
    quote_specs = getattr(quote, "specs", None) or {}
    quote_cost_breakdown = getattr(quote, "cost_breakdown", None) or {}
    customer_address = _safe_str(quote_specs.get("customer_address", ""))
    payment_details = _safe_str(
        quote_specs.get("payment_details") or quote_cost_breakdown.get("payment_details", "")
    )
    
    # Get line items from related models (NEW APPROACH)
    line_items = quote.line_items.all()
    costs = quote.costs.all()
    
    # Calculate totals dynamically from line items and costs
    materials_total = sum((item.line_total for item in line_items), Decimal("0"))
    labour_total = sum((c.amount for c in costs.filter(cost_type="labour")), Decimal("0"))
    transport_total = sum((c.amount for c in costs.filter(cost_type="transport")), Decimal("0"))
    other_total = sum((c.amount for c in costs.filter(cost_type="other")), Decimal("0"))
    profit_total = sum((c.amount for c in costs.filter(cost_type="profit")), Decimal("0"))
    
    subtotal = materials_total + labour_total + transport_total + other_total
    total = subtotal + profit_total
    
    # Create PDF buffer
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2 * cm,
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        "QuoteTitle",
        parent=styles["Heading1"],
        fontSize=28,
        textColor=BRAND_DARK,
        spaceAfter=6,
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
    )
    
    heading_style = ParagraphStyle(
        "QuoteHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=BRAND_ORANGE,
        spaceAfter=4,
        spaceBefore=16,
        fontName="Helvetica-Bold",
    )
    
    normal_style = ParagraphStyle(
        "QuoteNormal",
        parent=styles["Normal"],
        fontSize=10,
        textColor=BRAND_DARK,
        spaceAfter=4,
    )
    
    small_style = ParagraphStyle(
        "QuoteSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=BRAND_GRAY,
    )
    
    # ===========================================================================
    # HEADER - Business name with centered initials badge (professional)
    # ===========================================================================
    
    # Create centered header with logo when available.
    logo_path = _safe_str(getattr(business_logo, "path", ""))
    logo_rendered = False
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=2.2 * cm, height=2.2 * cm)
            logo.hAlign = "CENTER"
            story.append(logo)
            story.append(Spacer(1, 0.2 * cm))
            logo_rendered = True
        except Exception as e:
            logger.warning("Could not render business logo for quote PDF: %s", e)
    
    # Centered business name
    centered_title_style = ParagraphStyle(
        "CenteredTitle",
        parent=title_style,
        alignment=TA_CENTER,
    )
    
    if logo_rendered:
        business_title_style = ParagraphStyle(
            "LogoBusinessName",
            parent=centered_title_style,
            fontSize=14,
        )
    else:
        business_title_style = centered_title_style

    story.append(Paragraph(f"<b>{business_name}</b>", business_title_style))
    story.append(Spacer(1, 0.3 * cm))
    
    # Quotation header centered
    quotation_header_style = ParagraphStyle(
        "QuotationHeader",
        parent=heading_style,
        fontSize=18,
        alignment=TA_CENTER,
        textColor=BRAND_ORANGE,
        spaceAfter=2,
    )
    story.append(Paragraph("<b>QUOTATION</b>", quotation_header_style))
    story.append(Paragraph(f"<font size='11'>{quote_number}</font>", 
                          ParagraphStyle("CenterGray", parent=small_style, alignment=TA_CENTER, fontSize=11)))
    
    # Business contact line
    contact_parts = []
    if business_phone:
        contact_parts.append(business_phone)
    if business_email:
        contact_parts.append(business_email)
    if business_address:
        contact_parts.append(business_address)
    
    if contact_parts:
        story.append(Paragraph(" · ".join(contact_parts), small_style))
    
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e5e5")))
    story.append(Spacer(1, 0.5 * cm))
    
    # ===========================================================================
    # QUOTE INFO & CUSTOMER
    # ===========================================================================
    
    # Two-column layout: Quote details | Customer details
    quote_date_str = created_at.strftime('%B %d, %Y') if created_at else "N/A"
    valid_str = valid_until.strftime('%B %d, %Y') if valid_until else "30 days from issue"
    
    left_col = [
        Paragraph("<b>Quote Details</b>", heading_style),
        Paragraph(f"Date: {quote_date_str}", normal_style),
        Paragraph(f"Valid Until: {valid_str}", normal_style),
    ]
    
    right_col = [
        Paragraph("<b>Customer</b>", heading_style),
        Paragraph(f"<b>{customer_name}</b>", normal_style),
    ]
    if customer_phone:
        right_col.append(Paragraph(customer_phone, small_style))
    if customer_email:
        right_col.append(Paragraph(customer_email, small_style))
    
    # Build as nested tables for proper layout
    info_data = [[
        [p for p in left_col],
        [p for p in right_col],
    ]]
    
    # Create simple side-by-side paragraphs instead
    story.append(Paragraph("<b>Quote Details</b>", heading_style))
    story.append(Paragraph(f"Date Issued: {quote_date_str}", normal_style))
    story.append(Paragraph(f"Valid Until: {valid_str}", normal_style))
    
    story.append(Paragraph("<b>Prepared For</b>", heading_style))
    story.append(Paragraph(f"<b>{customer_name}</b>", normal_style))
    if customer_phone:
        story.append(Paragraph(f"Phone: {customer_phone}", normal_style))
    if customer_email:
        story.append(Paragraph(f"Email: {customer_email}", normal_style))
    if customer_address:
        story.append(Paragraph(f"Address: {customer_address}", normal_style))
    
    story.append(Spacer(1, 0.5 * cm))
    
    # ===========================================================================
    # ITEMS TABLE
    # ===========================================================================
    
    story.append(Paragraph("<b>Materials & Items</b>", heading_style))
    
    # Table header
    table_data = [["Description", "Unit", "Qty", "Unit Price", "Amount"]]
    
    # Add line items from the new model
    if line_items:
        for item in line_items:
            try:
                desc = _safe_str(item.material_name, "Item")
                unit = _safe_str(item.material_unit, "pc")
                qty = _safe_str(item.quantity, "1")
                unit_price = _safe_decimal(item.unit_price)
                line_total = _safe_decimal(item.line_total)
                
                table_data.append([
                    desc,
                    unit,
                    qty,
                    f"MWK {unit_price:,.0f}" if unit_price > 0 else "TBD",
                    f"MWK {line_total:,.0f}",
                ])
            except Exception as e:
                logger.warning(f"Error rendering line item: {e}")
                # Add placeholder row
                table_data.append([desc, unit, qty, "Error", "Error"])
    else:
        # No items - add placeholder
        table_data.append(["No items added", "", "", "", "MWK 0"])
    
    # Create table
    items_table = Table(
        table_data, 
        colWidths=[8*cm, 2*cm, 1.5*cm, 2.5*cm, 3*cm]
    )
    items_table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_ORANGE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        # Data
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), BRAND_DARK),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        # Grid
        ("LINEBELOW", (0, 0), (-1, 0), 1, BRAND_ORANGE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, colors.HexColor("#e5e5e5")),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#e5e5e5")),
    ]))
    
    story.append(items_table)
    story.append(Spacer(1, 0.5 * cm))
    
    # ===========================================================================
    # TOTALS
    # ===========================================================================
    
    totals_data = []
    
    if materials_total > 0:
        totals_data.append(["Materials Subtotal:", f"MWK {materials_total:,.0f}"])
    if labour_total > 0:
        totals_data.append(["Labour:", f"MWK {labour_total:,.0f}"])
    if transport_total > 0:
        totals_data.append(["Transport:", f"MWK {transport_total:,.0f}"])
    if other_total > 0:
        totals_data.append(["Other Costs:", f"MWK {other_total:,.0f}"])
    
    totals_data.append(["", ""])  # Spacer row
    totals_data.append(["SUBTOTAL:", f"MWK {subtotal:,.0f}"])
    
    if profit_total > 0:
        totals_data.append(["Profit/Markup:", f"MWK {profit_total:,.0f}"])
    
    totals_data.append(["", ""])  # Spacer row
    totals_data.append(["TOTAL:", f"MWK {total:,.0f}"])
    
    totals_table = Table(totals_data, colWidths=[12*cm, 5*cm])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -2), 10),
        ("TEXTCOLOR", (0, 0), (-1, -2), BRAND_GRAY),
        # Total row
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 14),
        ("TEXTCOLOR", (0, -1), (-1, -1), BRAND_DARK),
        ("LINEABOVE", (0, -1), (-1, -1), 2, BRAND_ORANGE),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
    ]))
    
    story.append(totals_table)
    story.append(Spacer(1, 1 * cm))

    try:
        from inventory.services.welding_finance import format_percent, quote_payment_milestones

        milestones = quote_payment_milestones(quote)
    except Exception:
        format_percent = lambda value: format(_safe_decimal(value), "f").rstrip("0").rstrip(".") or "0"
        milestones = []

    if milestones:
        story.append(Paragraph("<b>Payment Milestones</b>", heading_style))
        milestone_data = [["Milestone", "Percent", "Amount"]]
        for milestone in milestones:
            percent = _safe_decimal(milestone.get("percent"))
            amount = (total * percent / Decimal("100")).quantize(Decimal("0.01"))
            milestone_data.append([
                _safe_str(milestone.get("label"), "Payment"),
                f"{format_percent(percent)}%",
                f"MWK {amount:,.0f}",
            ])
        milestone_table = Table(milestone_data, colWidths=[9 * cm, 3 * cm, 5 * cm])
        milestone_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e5e5")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(milestone_table)
        story.append(Spacer(1, 0.5 * cm))

    if payment_details:
        story.append(Paragraph("<b>Payment Details</b>", heading_style))
        story.append(Paragraph(payment_details, small_style))
        story.append(Spacer(1, 0.5 * cm))
    
    # ===========================================================================
    # TERMS & FOOTER
    # ===========================================================================
    
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e5e5")))
    story.append(Spacer(1, 0.5 * cm))
    
    story.append(Paragraph("<b>Terms & Conditions</b>", heading_style))
    terms_text = """
    • This quotation is valid for 30 days from the date of issue.
    • A 50% deposit is required to commence work.
    • Final payment is due upon completion before delivery.
    • Prices include materials and labour as specified.
    • Additional work or changes may incur extra charges.
    """
    terms_text = _safe_str(getattr(quote, "terms", ""), "") or terms_text
    story.append(Paragraph(terms_text, small_style))
    
    story.append(Spacer(1, 1 * cm))
    
    # Thank you message
    thank_you_style = ParagraphStyle(
        "ThankYou",
        parent=normal_style,
        fontSize=11,
        textColor=BRAND_ORANGE,
        alignment=TA_CENTER,
    )
    story.append(Paragraph("<b>Thank you for choosing us!</b>", thank_you_style))
    story.append(Paragraph(f"Generated on {timezone.now().strftime('%B %d, %Y at %H:%M')}", 
                          ParagraphStyle("Footer", parent=small_style, alignment=TA_CENTER)))
    
    # Build PDF
    doc.build(story)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    logger.info(f"Quote PDF generated: {quote_number} ({len(pdf_bytes)} bytes)")
    return pdf_bytes


def _generate_fallback_pdf(quote) -> bytes:
    """Generate a minimal fallback PDF when main generation fails."""
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # Simple content
    story.append(Paragraph("<b>QUOTATION</b>", styles["Heading1"]))
    story.append(Spacer(1, 1 * cm))
    
    quote_number = _safe_str(getattr(quote, 'quote_number', None), "Quote")
    customer_name = _safe_str(getattr(quote, 'customer_name', None), "Customer")
    total = _safe_decimal(getattr(quote, 'total', None))
    
    story.append(Paragraph(f"Quote: {quote_number}", styles["Normal"]))
    story.append(Paragraph(f"Customer: {customer_name}", styles["Normal"]))
    story.append(Paragraph(f"Total: MWK {total:,.0f}", styles["Normal"]))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    
    doc.build(story)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes

