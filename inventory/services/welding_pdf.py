from __future__ import annotations

import io
import logging
import os
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False


BRAND_ORANGE = colors.HexColor("#f97316") if REPORTLAB_AVAILABLE else None
BRAND_DARK = colors.HexColor("#111827") if REPORTLAB_AVAILABLE else None
BRAND_GRAY = colors.HexColor("#6b7280") if REPORTLAB_AVAILABLE else None
LINE_GRAY = colors.HexColor("#e5e7eb") if REPORTLAB_AVAILABLE else None


def _safe_str(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _money(value) -> str:
    try:
        amount = Decimal(str(value or "0"))
    except Exception:
        amount = Decimal("0")
    return f"MWK {amount:,.0f}"


def _local_image_path(file_field) -> str:
    if not file_field:
        return ""
    try:
        path = getattr(file_field, "path", "")
    except Exception:
        return ""
    return path if path and os.path.exists(path) else ""


def generate_quote_pdf(quote, business=None):
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab is not installed. Cannot generate welding quote PDF.")
        return None
    try:
        return _generate_quote_pdf(quote, business or quote.business)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Could not generate welding quote PDF: %s", exc)
        return _fallback_pdf(quote)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=28,
            textColor=BRAND_DARK,
            alignment=TA_RIGHT,
        ),
        "company": ParagraphStyle(
            "Company",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=BRAND_DARK,
            spaceAfter=4,
        ),
        "heading": ParagraphStyle(
            "Heading",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=BRAND_ORANGE,
            spaceBefore=8,
            spaceAfter=5,
        ),
        "normal": ParagraphStyle(
            "Normal",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=BRAND_DARK,
        ),
        "muted": ParagraphStyle(
            "Muted",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            textColor=BRAND_GRAY,
        ),
        "right": ParagraphStyle(
            "Right",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            alignment=TA_RIGHT,
            textColor=BRAND_DARK,
        ),
        "small_left": ParagraphStyle(
            "SmallLeft",
            parent=base["Normal"],
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
            textColor=BRAND_DARK,
        ),
    }


def _paragraph_lines(lines: list[str], style):
    return Paragraph("<br/>".join(line for line in lines if line), style)


def _generate_quote_pdf(quote, business) -> bytes:
    from inventory.services.welding_branding import branding_profile_for_quote
    from inventory.services.welding_finance import format_percent, quote_payment_milestones, quote_totals

    profile = branding_profile_for_quote(quote, business)
    totals = quote_totals(quote)
    line_items = list(quote.line_items.all())
    costs = list(quote.costs.all())
    styles = _styles()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.5 * cm,
    )
    story = []

    logo_path = _local_image_path(profile.logo)
    logo_or_name = Image(logo_path, width=3.0 * cm, height=2.0 * cm) if logo_path else Paragraph(profile.company_name, styles["company"])
    company_lines = []
    if profile.phone:
        company_lines.append(profile.phone)
    if profile.email:
        company_lines.append(profile.email)
    if profile.address:
        company_lines.append(profile.address.replace("\n", "<br/>"))
    if profile.city:
        company_lines.append(profile.city)

    header = Table(
        [
            [
                logo_or_name,
                [
                    Paragraph("QUOTATION", styles["title"]),
                    Paragraph(f"<b>{_safe_str(quote.quote_number)}</b>", styles["right"]),
                    Paragraph(timezone.localtime(quote.created_at).strftime("%d %b %Y"), styles["right"]),
                ],
            ],
            [Paragraph(profile.company_name, styles["company"]) if logo_path else "", ""],
            [_paragraph_lines(company_lines, styles["muted"]), ""],
        ],
        colWidths=[10.5 * cm, 6.5 * cm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, BRAND_ORANGE),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.45 * cm))

    customer_lines = [
        f"<b>{_safe_str(quote.customer_name, 'Customer')}</b>",
        f"Contact: {_safe_str(quote.customer_contact_person)}" if getattr(quote, "customer_contact_person", "") else "",
        f"Phone: {_safe_str(quote.customer_phone)}" if quote.customer_phone else "",
        f"Email: {_safe_str(quote.customer_email)}" if quote.customer_email else "",
        _safe_str(getattr(quote, "customer_address", "")).replace("\n", "<br/>"),
    ]
    quote_lines = [
        f"Quote No: <b>{_safe_str(quote.quote_number)}</b>",
        f"Date: {timezone.localtime(quote.created_at).strftime('%d %b %Y')}",
        f"Status: {quote.get_status_display()}",
        f"Valid Until: {quote.valid_until.strftime('%d %b %Y')}" if quote.valid_until else "Valid for 30 days from issue",
    ]
    info = Table(
        [
            [Paragraph("CUSTOMER DETAILS", styles["heading"]), Paragraph("QUOTE DETAILS", styles["heading"])],
            [_paragraph_lines(customer_lines, styles["normal"]), _paragraph_lines(quote_lines, styles["normal"])],
        ],
        colWidths=[8.5 * cm, 8.5 * cm],
    )
    info.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(info)
    story.append(Spacer(1, 0.5 * cm))

    rows = [["#", "Description", "Quantity", "Unit Price", "Total"]]
    index = 1
    for item in line_items:
        rows.append([
            str(index),
            Paragraph(_safe_str(item.material_name, "Item"), styles["small_left"]),
            f"{item.quantity} {item.material_unit}",
            _money(item.unit_price) if item.unit_price is not None else "TBD",
            _money(item.line_total),
        ])
        index += 1
    for cost in costs:
        rows.append([
            str(index),
            Paragraph(_safe_str(cost.description, cost.get_cost_type_display()), styles["small_left"]),
            "1",
            _money(cost.amount),
            _money(cost.amount),
        ])
        index += 1
    if len(rows) == 1:
        rows.append(["", "No items added", "", "", _money(0)])

    item_table = Table(rows, colWidths=[1 * cm, 7.2 * cm, 2.5 * cm, 3 * cm, 3.3 * cm], repeatRows=1)
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE_GRAY),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(item_table)
    story.append(Spacer(1, 0.35 * cm))

    total_rows = [
        ["Materials", _money(totals["materials_total"])],
        ["Labour", _money(totals["labour_total"])],
        ["Transport", _money(totals["transport_total"])],
        ["Other", _money(totals["other_total"])],
        ["Profit", _money(totals["profit_total"])],
        ["Grand Total", _money(totals["grand_total"])],
    ]
    totals_table = Table(total_rows, colWidths=[4.2 * cm, 4 * cm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fff7ed")),
        ("LINEABOVE", (0, -1), (-1, -1), 1, BRAND_ORANGE),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(totals_table)

    milestones = quote_payment_milestones(quote)
    if milestones:
        story.append(Paragraph("PAYMENT MILESTONES", styles["heading"]))
        milestone_rows = [["Milestone", "Percent", "Amount"]]
        for milestone in milestones:
            percent_text = format_percent(milestone.get("percent"))
            percent = Decimal(percent_text)
            amount = totals["grand_total"] * percent / Decimal("100")
            milestone_rows.append([_safe_str(milestone.get("label"), "Payment"), f"{percent_text}%", _money(amount)])
        milestone_table = Table(milestone_rows, colWidths=[8 * cm, 3 * cm, 4 * cm])
        milestone_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f9fafb")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.35, LINE_GRAY),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(milestone_table)

    story.append(Spacer(1, 0.4 * cm))
    terms = _safe_str(getattr(quote, "terms", ""), profile.terms)
    payment = profile.payment_instructions or _safe_str((getattr(quote, "cost_breakdown", {}) or {}).get("payment_details"))
    bottom = Table(
        [
            [Paragraph("TERMS AND CONDITIONS", styles["heading"]), Paragraph("PAYMENT INSTRUCTIONS", styles["heading"])],
            [Paragraph(terms.replace("\n", "<br/>"), styles["muted"]), Paragraph((payment or "Payment details will be confirmed with the customer.").replace("\n", "<br/>"), styles["muted"])],
        ],
        colWidths=[8.5 * cm, 8.5 * cm],
    )
    bottom.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(bottom)

    sig_path = _local_image_path(profile.signature_image)
    signature_parts = []
    if sig_path:
        signature_parts.append(Image(sig_path, width=4 * cm, height=1.4 * cm))
    signature_parts.append(Paragraph(f"Authorized by: <b>{profile.signature_name or profile.company_name}</b>", styles["normal"]))
    signature = Table([[signature_parts]], colWidths=[7 * cm], hAlign="RIGHT")
    signature.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, -1), 0.6, BRAND_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(Spacer(1, 0.7 * cm))
    story.append(signature)
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Generated by Emajinet", ParagraphStyle("Footer", parent=styles["muted"], alignment=TA_RIGHT)))

    doc.build(story)
    return buffer.getvalue()


def _fallback_pdf(quote) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    doc.build([
        Paragraph("Welding Quotation", styles["Heading1"]),
        Paragraph(f"Quote: {_safe_str(getattr(quote, 'quote_number', ''), 'N/A')}", styles["Normal"]),
        Paragraph(f"Customer: {_safe_str(getattr(quote, 'customer_name', ''), 'Customer')}", styles["Normal"]),
    ])
    return buffer.getvalue()
