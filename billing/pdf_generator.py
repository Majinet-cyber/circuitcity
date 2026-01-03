# billing/pdf_generator.py
"""
Invoice PDF generation using ReportLab.
Generates professional, branded invoices for download.
"""
from __future__ import annotations

import io
import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.utils import timezone

from .models import PaymentTransaction

logger = logging.getLogger(__name__)

# Graceful ReportLab imports
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("ReportLab not installed. Invoice PDF generation will not work.")


def generate_invoice_pdf(invoice, output_path: Optional[str] = None) -> Optional[bytes]:
    """
    Generate PDF for invoice.

    Args:
        invoice: Invoice model instance
        output_path: Optional file path to save PDF (if None, returns bytes)

    Returns:
        PDF bytes if output_path is None, else None
    """
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab not installed. Cannot generate PDF.")
        return None

    # Create PDF buffer
    if output_path:
        buffer = open(output_path, "wb")
    else:
        buffer = io.BytesIO()

    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
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
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#333333"),
        spaceAfter=6,
        spaceBefore=12,
    )

    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#333333"),
    )

    small_style = ParagraphStyle(
        "CustomSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
    )

    # Header: Company Name / Logo
    story.append(Paragraph("Emajinet / Circuit City", title_style))
    story.append(Paragraph("Business Management Platform", small_style))
    story.append(Spacer(1, 0.5 * cm))

    # Invoice Title and Number
    story.append(Paragraph(f"<b>INVOICE</b>", heading_style))
    story.append(Paragraph(f"Invoice Number: {invoice.number}", normal_style))
    story.append(Paragraph(f"Issue Date: {invoice.issue_date.strftime('%B %d, %Y')}", normal_style))

    if invoice.due_date:
        story.append(Paragraph(f"Due Date: {invoice.due_date.strftime('%B %d, %Y')}", normal_style))

    story.append(Spacer(1, 0.5 * cm))

    # Bill To Section
    story.append(Paragraph("<b>Bill To:</b>", heading_style))

    if invoice.business:
        story.append(Paragraph(invoice.business.name, normal_style))

        # Business contact info
        if hasattr(invoice.business, "email") and invoice.business.email:
            story.append(Paragraph(invoice.business.email, small_style))
        if hasattr(invoice.business, "phone") and invoice.business.phone:
            story.append(Paragraph(invoice.business.phone, small_style))

    if invoice.to_name:
        story.append(Paragraph(invoice.to_name, normal_style))
    if invoice.to_email:
        story.append(Paragraph(invoice.to_email, small_style))

    story.append(Spacer(1, 0.5 * cm))

    # Billing Period (if applicable)
    if invoice.billing_period_start and invoice.billing_period_end:
        story.append(Paragraph("<b>Billing Period:</b>", heading_style))
        story.append(
            Paragraph(
                f"{invoice.billing_period_start.strftime('%B %d, %Y')} - "
                f"{invoice.billing_period_end.strftime('%B %d, %Y')}",
                normal_style,
            )
        )
        story.append(Spacer(1, 0.5 * cm))

    # Line Items Table
    table_data = [["Description", "Qty", "Unit", "Unit Price", "Amount"]]

    for item in invoice.items.all():
        table_data.append(
            [
                item.description,
                str(item.qty),
                item.unit,
                f"{invoice.currency} {item.unit_price:,.2f}",
                f"{invoice.currency} {item.line_total:,.2f}",
            ]
        )

    # Create table
    table = Table(table_data, colWidths=[8 * cm, 2 * cm, 2 * cm, 3 * cm, 3 * cm])
    table.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                # Data rows
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#333333")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),  # Align numbers right
                ("ALIGN", (0, 1), (0, -1), "LEFT"),  # Align description left
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ]
        )
    )

    story.append(table)
    story.append(Spacer(1, 0.5 * cm))

    # Totals Table (right-aligned)
    totals_data = [
        ["Subtotal:", f"{invoice.currency} {invoice.subtotal:,.2f}"],
    ]

    if invoice.tax_amount > 0:
        totals_data.append(["Tax:", f"{invoice.currency} {invoice.tax_amount:,.2f}"])

    totals_data.append(["<b>Total:</b>", f"<b>{invoice.currency} {invoice.total:,.2f}</b>"])

    totals_table = Table(totals_data, colWidths=[10 * cm, 8 * cm])
    totals_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                # Bold last row (total)
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, -1), (-1, -1), 11),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#333333")),
            ]
        )
    )

    story.append(totals_table)
    story.append(Spacer(1, 1 * cm))

    # Payment Status
    status_text = f"<b>Status:</b> {invoice.get_status_display()}"
    if invoice.paid_at:
        status_text += f" (Paid on {invoice.paid_at.strftime('%B %d, %Y')})"

    story.append(Paragraph(status_text, normal_style))

    # Payment Reference (if available)
    if invoice.provider_reference:
        story.append(Paragraph(f"Payment Reference: {invoice.provider_reference}", small_style))

    story.append(Spacer(1, 1 * cm))

    # Notes (if any)
    if invoice.notes:
        story.append(Paragraph("<b>Notes:</b>", heading_style))
        story.append(Paragraph(invoice.notes, small_style))
        story.append(Spacer(1, 0.5 * cm))

    # Footer
    story.append(Spacer(1, 1 * cm))
    footer_text = "Thank you for your business!<br/>" f"Generated on {timezone.now().strftime('%B %d, %Y at %H:%M')}"
    story.append(Paragraph(footer_text, small_style))

    # Build PDF
    try:
        doc.build(story)

        if output_path:
            buffer.close()
            logger.info(f"Invoice PDF generated: {invoice.number} -> {output_path}")
            return None
        else:
            pdf_bytes = buffer.getvalue()
            buffer.close()
            logger.info(f"Invoice PDF generated: {invoice.number} ({len(pdf_bytes)} bytes)")
            return pdf_bytes

    except Exception as e:
        logger.error(f"Error generating PDF for invoice {invoice.number}: {e}", exc_info=True)
        if not output_path:
            buffer.close()
        return None


def generate_and_save_invoice_pdf(invoice) -> bool:
    """
    Generate PDF and save to invoice.pdf_file field.

    Args:
        invoice: Invoice model instance

    Returns:
        True if successful, False otherwise
    """
    from django.core.files.base import ContentFile

    # Generate PDF bytes
    pdf_bytes = generate_invoice_pdf(invoice)

    if not pdf_bytes:
        logger.error(f"Failed to generate PDF for invoice {invoice.number}")
        return False

    # Save to FileField
    filename = f"invoice_{invoice.number}.pdf"
    invoice.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    invoice.pdf_generated_at = timezone.now()
    invoice.save(update_fields=["pdf_file", "pdf_generated_at", "updated_at"])

    logger.info(f"Invoice PDF saved: {invoice.number} -> {invoice.pdf_file.name}")

    return True


def generate_payment_receipt_pdf(payment) -> Optional[bytes]:
    """
    Generate receipt PDF for a Payment.

    Args:
        payment: Payment model instance

    Returns:
        PDF bytes or None
    """
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab not installed. Cannot generate receipt PDF.")
        return None

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

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#333333"),
        spaceAfter=6,
        spaceBefore=12,
    )

    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#333333"),
    )

    small_style = ParagraphStyle(
        "CustomSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
    )

    # Header
    story.append(Paragraph("Emajinet / Circuit City", title_style))
    story.append(Paragraph("Payment Receipt", heading_style))
    story.append(Spacer(1, 0.5 * cm))

    # Payment details
    story.append(Paragraph("<b>Payment Details:</b>", heading_style))
    story.append(Paragraph(f"Payment Reference: {payment.reference or payment.external_id or 'N/A'}", normal_style))
    story.append(Paragraph(f"Amount: {payment.currency} {payment.amount:,.2f}", normal_style))
    story.append(Paragraph(f"Status: {payment.get_status_display()}", normal_style))
    story.append(Paragraph(f"Provider: {payment.get_provider_display()}", normal_style))
    story.append(
        Paragraph(
            f"Date: {payment.processed_at.strftime('%B %d, %Y at %H:%M') if payment.processed_at else payment.created_at.strftime('%B %d, %Y at %H:%M')}",
            normal_style,
        )
    )

    story.append(Spacer(1, 0.5 * cm))

    # Business info
    if payment.business:
        story.append(Paragraph("<b>Business:</b>", heading_style))
        story.append(Paragraph(payment.business.name, normal_style))

    story.append(Spacer(1, 0.5 * cm))

    # Invoice link
    if payment.invoice:
        story.append(Paragraph("<b>Related Invoice:</b>", heading_style))
        story.append(Paragraph(f"Invoice Number: {payment.invoice.number}", normal_style))
        if payment.invoice.billing_period_start and payment.invoice.billing_period_end:
            story.append(
                Paragraph(
                    f"Period: {payment.invoice.billing_period_start.strftime('%B %d, %Y')} - "
                    f"{payment.invoice.billing_period_end.strftime('%B %d, %Y')}",
                    normal_style,
                )
            )

    story.append(Spacer(1, 1 * cm))

    # Footer
    footer_text = f"Generated on {timezone.now().strftime('%B %d, %Y at %H:%M')}"
    story.append(Paragraph(footer_text, small_style))

    try:
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        logger.info(f"Payment receipt PDF generated: payment {payment.id} ({len(pdf_bytes)} bytes)")
        return pdf_bytes
    except Exception as e:
        logger.error(f"Error generating receipt PDF for payment {payment.id}: {e}", exc_info=True)
        buffer.close()
        return None


def generate_transaction_receipt_pdf(transaction) -> Optional[bytes]:
    """
    Generate receipt PDF for a PaymentTransaction.

    Args:
        transaction: PaymentTransaction model instance

    Returns:
        PDF bytes or None
    """
    if not REPORTLAB_AVAILABLE:
        logger.error("ReportLab not installed. Cannot generate receipt PDF.")
        return None

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

    # Custom styles (same as payment receipt)
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#333333"),
        spaceAfter=6,
        spaceBefore=12,
    )

    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#333333"),
    )

    small_style = ParagraphStyle(
        "CustomSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#666666"),
    )

    # Header
    story.append(Paragraph("Emajinet / Circuit City", title_style))
    story.append(Paragraph("Payment Receipt", heading_style))
    story.append(Spacer(1, 0.5 * cm))

    # Transaction details
    story.append(Paragraph("<b>Transaction Details:</b>", heading_style))
    story.append(Paragraph(f"Transaction Reference: {transaction.tx_ref}", normal_style))
    story.append(Paragraph(f"Amount: {transaction.currency} {transaction.amount:,.2f}", normal_style))
    story.append(Paragraph(f"Status: {transaction.get_status_display()}", normal_style))
    story.append(Paragraph(f"Provider: {transaction.provider.title()}", normal_style))
    story.append(
        Paragraph(
            f"Date: {transaction.updated_at.strftime('%B %d, %Y at %H:%M') if transaction.status == PaymentTransaction.Status.SUCCESS else transaction.created_at.strftime('%B %d, %Y at %H:%M')}",
            normal_style,
        )
    )

    if transaction.charge_id:
        story.append(Paragraph(f"Charge ID: {transaction.charge_id}", normal_style))

    story.append(Spacer(1, 0.5 * cm))

    # Business info
    if transaction.business:
        story.append(Paragraph("<b>Business:</b>", heading_style))
        story.append(Paragraph(transaction.business.name, normal_style))

    story.append(Spacer(1, 1 * cm))

    # Footer
    footer_text = f"Generated on {timezone.now().strftime('%B %d, %Y at %H:%M')}"
    story.append(Paragraph(footer_text, small_style))

    try:
        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        logger.info(f"Transaction receipt PDF generated: transaction {transaction.id} ({len(pdf_bytes)} bytes)")
        return pdf_bytes
    except Exception as e:
        logger.error(f"Error generating receipt PDF for transaction {transaction.id}: {e}", exc_info=True)
        buffer.close()
        return None
