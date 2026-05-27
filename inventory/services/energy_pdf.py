# inventory/services/energy_pdf.py
"""
Premium PDF generation for the Renewable Energy vertical.

Generates polished, branded documents:
- System sizing proposal
- Engineering report
- Customer-facing summary
- Site performance report
- Executive summary

Uses ReportLab following the same robust pattern as welding_pdf.py:
must NEVER fail — always return a valid PDF even with missing data.
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, HRFlowable, PageBreak,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not installed. Energy PDF generation unavailable.")


BRAND_GREEN = colors.HexColor("#10b981")
BRAND_GREEN_DARK = colors.HexColor("#059669")
BRAND_DARK = colors.HexColor("#0f172a")
BRAND_GRAY = colors.HexColor("#64748b")
BRAND_LIGHT = colors.HexColor("#f8fafc")
BRAND_ACCENT = colors.HexColor("#6366f1")
BRAND_WARN = colors.HexColor("#f59e0b")


def _safe(val, default=""):
    if val is None:
        return str(default)
    return str(val).strip() or str(default)


def _fmt_num(val, suffix="", decimals=0):
    if val is None:
        return "–"
    try:
        v = float(val)
        if decimals == 0:
            formatted = f"{v:,.0f}"
        else:
            formatted = f"{v:,.{decimals}f}"
        return f"{formatted}{suffix}" if suffix else formatted
    except (ValueError, TypeError):
        return "–"


def _fmt_currency(val, currency="MWK"):
    if val is None:
        return "–"
    try:
        return f"{currency} {float(val):,.0f}"
    except (ValueError, TypeError):
        return "–"


def _get_styles():
    styles = getSampleStyleSheet()
    custom = {
        "doc_title": ParagraphStyle("DocTitle", parent=styles["Heading1"], fontSize=26, textColor=BRAND_DARK, spaceAfter=4, fontName="Helvetica-Bold"),
        "doc_subtitle": ParagraphStyle("DocSubtitle", parent=styles["Normal"], fontSize=13, textColor=BRAND_GRAY, spaceAfter=8),
        "section": ParagraphStyle("Section", parent=styles["Heading2"], fontSize=13, textColor=BRAND_GREEN_DARK, spaceBefore=16, spaceAfter=6, fontName="Helvetica-Bold"),
        "subsection": ParagraphStyle("Subsection", parent=styles["Heading3"], fontSize=11, textColor=BRAND_ACCENT, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold"),
        "body": ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, textColor=BRAND_DARK, spaceAfter=4),
        "small": ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=BRAND_GRAY),
        "bold": ParagraphStyle("Bold", parent=styles["Normal"], fontSize=10, textColor=BRAND_DARK, fontName="Helvetica-Bold"),
        "center": ParagraphStyle("Center", parent=styles["Normal"], fontSize=10, textColor=BRAND_DARK, alignment=TA_CENTER),
        "warn": ParagraphStyle("Warn", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#dc2626"), spaceAfter=3),
        "rec": ParagraphStyle("Rec", parent=styles["Normal"], fontSize=9, textColor=BRAND_GREEN_DARK, spaceAfter=3),
    }
    return custom


def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"))


# ---------------------------------------------------------------------------
# System Sizing Proposal PDF
# ---------------------------------------------------------------------------

def generate_sizing_pdf(run, business=None) -> Optional[bytes]:
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab not available for sizing PDF.")
        return None
    try:
        return _build_sizing_pdf(run, business)
    except Exception as e:
        logger.error(f"Sizing PDF error: {e}", exc_info=True)
        try:
            return _fallback_pdf("System Sizing Proposal", str(e))
        except Exception:
            return None


def _build_sizing_pdf(run, business=None) -> bytes:
    business = business or getattr(run, "business", None)
    biz_name = _safe(getattr(business, "name", None), "Energy Business")
    currency = _safe(getattr(business, "currency", None), "MWK")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=1.5*cm, bottomMargin=2*cm)
    story = []
    s = _get_styles()

    # === COVER / HEADER ===
    story.append(Paragraph(f"<b>{biz_name}</b>", s["doc_title"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph("<b>SYSTEM SIZING PROPOSAL</b>",
                           ParagraphStyle("ProposalTitle", parent=s["section"], fontSize=18, alignment=TA_CENTER, textColor=BRAND_GREEN_DARK)))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"{_safe(run.title, 'Untitled')} — Version {run.version}", s["center"]))
    ref = _safe(run.reference_code)
    if ref:
        story.append(Paragraph(f"Ref: {ref}", ParagraphStyle("Ref", parent=s["small"], alignment=TA_CENTER)))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        f"Prepared: {run.created_at.strftime('%B %d, %Y') if run.created_at else 'N/A'} | "
        f"Status: {_safe(run.status, 'Draft').title()}",
        ParagraphStyle("Meta", parent=s["small"], alignment=TA_CENTER),
    ))
    story.append(Spacer(1, 0.4*cm))
    story.append(_hr())

    # === CUSTOMER INFO ===
    story.append(Paragraph("<b>Prepared For</b>", s["section"]))
    customer_data = []
    if run.customer_name:
        customer_data.append(["Customer:", run.customer_name])
    if run.customer_phone:
        customer_data.append(["Phone:", run.customer_phone])
    if run.customer_email:
        customer_data.append(["Email:", run.customer_email])
    if run.customer_address:
        customer_data.append(["Address:", run.customer_address])
    site = getattr(run, "site", None)
    if site:
        customer_data.append(["Site:", site.name])
        if site.location:
            customer_data.append(["Location:", site.location])

    if customer_data:
        t = Table(customer_data, colWidths=[4*cm, 13*cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (0, -1), BRAND_GRAY),
            ("TEXTCOLOR", (1, 0), (1, -1), BRAND_DARK),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Customer details not provided.", s["body"]))
    story.append(Spacer(1, 0.3*cm))

    # === DESIGN PARAMETERS ===
    story.append(Paragraph("<b>Design Parameters</b>", s["section"]))
    params = [
        ["Design Objective:", _safe(run.get_design_objective_display(), run.design_objective)],
        ["System Architecture:", _safe(run.get_system_architecture_display(), run.system_architecture)],
        ["Peak Sun Hours:", f"{_fmt_num(run.peak_sun_hours, decimals=1)} hrs/day"],
        ["Panel Rating:", f"{run.panel_wattage} Wp"],
        ["Battery DoD:", f"{run.battery_dod_pct}%"],
        ["Battery Voltage:", f"{run.battery_voltage}V"],
        ["Autonomy Days:", _fmt_num(run.autonomy_days, decimals=1)],
        ["Diversity Factor:", _fmt_num(run.diversity_factor, decimals=2)],
        ["Growth Allowance:", f"{run.future_growth_pct}%"],
        ["Safety Margin:", f"{run.safety_margin_pct}%"],
    ]
    t = Table(params, colWidths=[5.5*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_GRAY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#f1f5f9")),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3*cm))

    # === LOAD SCHEDULE ===
    story.append(Paragraph("<b>Appliance / Load Schedule</b>", s["section"]))
    appliances = list(run.appliances.all())
    if appliances:
        header = ["Appliance", "Qty", "W", "Hrs/Day", "Daily Wh", "Priority"]
        rows = [header]
        for a in appliances:
            rows.append([
                _safe(a.name, "Item"),
                str(a.quantity),
                _fmt_num(a.wattage),
                _fmt_num(a.hours_per_day, decimals=1),
                _fmt_num(a.adjusted_daily_wh),
                _safe(a.get_priority_display(), a.priority),
            ])
        rows.append(["TOTAL", "", _fmt_num(run.peak_load_w), "", _fmt_num(run.total_daily_demand_wh), ""])

        t = Table(rows, colWidths=[5.5*cm, 1.5*cm, 2*cm, 2*cm, 3*cm, 3*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 1, BRAND_GREEN_DARK),
            ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, BRAND_GREEN_DARK),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No appliances entered.", s["body"]))

    story.append(PageBreak())

    # === ENGINEERING RESULTS ===
    story.append(Paragraph("<b>Engineering Results</b>", s["section"]))
    results = [
        ["Daily Energy Demand:", _fmt_num(run.total_daily_demand_kwh, " kWh", 2)],
        ["Corrected Design Load:", _fmt_num(run.corrected_design_load_wh, " Wh")],
        ["Peak Load:", _fmt_num(run.peak_load_w, " W")],
        ["Surge Load:", _fmt_num(run.surge_load_w, " W")],
        ["", ""],
        ["Solar Array:", f"{_fmt_num(run.recommended_array_kw, ' kW', 2)} ({run.recommended_panel_count or 0} panels)"],
        ["Battery Bank:", f"{_fmt_num(run.recommended_battery_kwh, ' kWh', 1)} total ({_fmt_num(run.usable_storage_kwh, ' kWh', 1)} usable)"],
        ["Inverter:", f"{_fmt_num(run.recommended_inverter_kw, ' kW')} (loading: {_fmt_num(run.inverter_loading_pct, '%', 0)})"],
        ["Charge Controller:", _fmt_num(run.recommended_charge_controller_a, " A", 0)],
    ]
    if run.has_generator and run.recommended_generator_kva:
        results.append(["Generator Backup:", _fmt_num(run.recommended_generator_kva, " kVA")])
    if run.estimated_runtime_hours:
        results.append(["Battery Runtime:", _fmt_num(run.estimated_runtime_hours, " hours", 1)])

    t = Table(results, colWidths=[5.5*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_GRAY),
        ("TEXTCOLOR", (1, 0), (1, -1), BRAND_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # === COST & ROI ===
    story.append(Paragraph("<b>Cost Estimate & ROI</b>", s["section"]))
    econ = [
        ["Equipment Cost (CapEx):", _fmt_currency(run.estimated_capex, currency)],
        ["Installation Cost:", _fmt_currency(run.estimated_installation_cost, currency)],
        ["Total Project Cost:", _fmt_currency(
            (run.estimated_capex or 0) + (run.estimated_installation_cost or 0), currency)],
        ["", ""],
        ["Monthly Grid Savings:", _fmt_currency(run.grid_savings_monthly, currency)],
    ]
    if run.diesel_offset_monthly and run.diesel_offset_monthly > 0:
        econ.append(["Monthly Diesel Offset:", _fmt_currency(run.diesel_offset_monthly, currency)])
    econ += [
        ["Projected Monthly Savings:", _fmt_currency(run.projected_monthly_savings, currency)],
        ["Projected Annual Savings:", _fmt_currency(run.projected_annual_savings, currency)],
        ["", ""],
        ["Payback Period:", _fmt_num(run.payback_years, " years", 1) if run.payback_years else "–"],
        ["ROI:", _fmt_num(run.roi_pct, "%", 1) if run.roi_pct else "–"],
        ["Lifetime Cost:", _fmt_currency(run.lifetime_cost_estimate, currency)],
        ["Cost per kWh:", _fmt_currency(run.cost_per_kwh, currency) if run.cost_per_kwh else "–"],
        ["Annual Maintenance:", _fmt_currency(run.estimated_annual_maintenance, currency)],
    ]
    t = Table(econ, colWidths=[6*cm, 11*cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_GRAY),
        ("TEXTCOLOR", (1, 0), (1, -1), BRAND_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # === RECOMMENDATIONS ===
    if run.recommendations:
        story.append(Paragraph("<b>Recommendations</b>", s["section"]))
        for r in run.recommendations:
            story.append(Paragraph(f"✓ {r}", s["rec"]))
        story.append(Spacer(1, 0.2*cm))

    if run.warnings:
        story.append(Paragraph("<b>Warnings</b>", s["subsection"]))
        for w in run.warnings:
            story.append(Paragraph(f"⚠ {w}", s["warn"]))
        story.append(Spacer(1, 0.2*cm))

    # === ASSUMPTIONS ===
    if run.assumptions or run.notes:
        story.append(Paragraph("<b>Assumptions & Notes</b>", s["section"]))
        if run.assumptions:
            story.append(Paragraph(run.assumptions, s["body"]))
        if run.notes:
            story.append(Paragraph(run.notes, s["body"]))

    # === FOOTER ===
    story.append(Spacer(1, 1*cm))
    story.append(_hr())
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("<b>Disclaimer</b>", s["subsection"]))
    story.append(Paragraph(
        "This sizing proposal is based on estimated loads and standard engineering assumptions. "
        "Actual system performance depends on installation quality, local conditions, and equipment specifications. "
        "Prices are indicative and subject to supplier quotes at time of procurement.",
        s["small"],
    ))
    story.append(Spacer(1, 0.5*cm))
    prepared = ""
    if run.prepared_by:
        name = getattr(run.prepared_by, "get_full_name", lambda: "")()
        prepared = f" by {name}" if name else ""
    story.append(Paragraph(
        f"Generated{prepared} on {timezone.now().strftime('%B %d, %Y at %H:%M')} | Powered by Emajinet",
        ParagraphStyle("Footer", parent=s["small"], alignment=TA_CENTER),
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    logger.info(f"Sizing PDF generated: {run.title} ({len(pdf_bytes)} bytes)")
    return pdf_bytes


# ---------------------------------------------------------------------------
# Site Performance Report PDF
# ---------------------------------------------------------------------------

def generate_site_report_pdf(site, business=None, readings=None, savings=None, alerts=None) -> Optional[bytes]:
    if not REPORTLAB_AVAILABLE:
        return None
    try:
        return _build_site_report_pdf(site, business, readings, savings, alerts)
    except Exception as e:
        logger.error(f"Site report PDF error: {e}", exc_info=True)
        return _fallback_pdf("Site Performance Report", str(e))


def _build_site_report_pdf(site, business=None, readings=None, savings=None, alerts=None) -> bytes:
    business = business or site.business
    currency = _safe(getattr(business, "currency", None), "MWK")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=1.5*cm, bottomMargin=2*cm)
    story = []
    s = _get_styles()

    story.append(Paragraph(f"<b>Site Performance Report</b>", s["doc_title"]))
    story.append(Paragraph(f"{site.name} — {site.get_site_type_display()}", s["doc_subtitle"]))
    story.append(Paragraph(f"Generated: {timezone.now().strftime('%B %d, %Y')}", s["small"]))
    story.append(Spacer(1, 0.3*cm))
    story.append(_hr())

    # Site info
    story.append(Paragraph("<b>Site Information</b>", s["section"]))
    info = [
        ["Status:", site.get_status_display()],
        ["Location:", _safe(site.location, "Not specified")],
        ["Customer:", _safe(site.customer_name, "–")],
        ["Installed Capacity:", _fmt_num(site.installed_capacity_kw, " kW", 2)],
        ["Commissioned:", str(site.commissioning_date) if site.commissioning_date else "–"],
        ["Months Operational:", str(site.months_operational or "–")],
    ]
    t = Table(info, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), BRAND_GRAY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    # Assets summary
    assets = list(site.assets.all())
    if assets:
        story.append(Paragraph("<b>Asset Summary</b>", s["section"]))
        header = ["Asset", "Type", "Health", "Status"]
        rows = [header]
        for a in assets:
            rows.append([str(a), a.get_asset_type_display(), f"{a.health_score}%", a.get_status_display()])
        t = Table(rows, colWidths=[6*cm, 4*cm, 3*cm, 4*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 1, BRAND_GREEN_DARK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(t)

    # Readings
    if readings:
        story.append(Paragraph("<b>Recent Energy Readings</b>", s["section"]))
        header = ["Date", "Generation (kWh)", "Consumption (kWh)", "Battery SOC"]
        rows = [header]
        for r in readings[:15]:
            rows.append([
                str(r.reading_date),
                _fmt_num(r.generation_kwh, decimals=1),
                _fmt_num(r.consumption_kwh, decimals=1),
                f"{r.battery_soc_pct}%" if r.battery_soc_pct is not None else "–",
            ])
        t = Table(rows, colWidths=[4*cm, 4.5*cm, 4.5*cm, 4*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, 0), 1, BRAND_ACCENT),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(t)

    # Footer
    story.append(Spacer(1, 1*cm))
    story.append(_hr())
    story.append(Paragraph(
        f"Powered by Emajinet — {timezone.now().strftime('%B %d, %Y')}",
        ParagraphStyle("Foot", parent=s["small"], alignment=TA_CENTER),
    ))

    doc.build(story)
    out = buf.getvalue()
    buf.close()
    return out


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _fallback_pdf(title: str, error_msg: str = "") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{title}</b>", styles["Heading1"]),
        Spacer(1, 1*cm),
        Paragraph("This document could not be fully generated.", styles["Normal"]),
        Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]),
    ]
    doc.build(story)
    out = buf.getvalue()
    buf.close()
    return out
