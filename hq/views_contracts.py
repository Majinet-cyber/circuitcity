# hq/views_contracts.py
"""
HQ views for managing merchant contracts and staff documentation.
"""
from __future__ import annotations

import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.uploadedfile import UploadedFile
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST

from hq.models import MerchantContract
from hq.permissions import hq_admin_required
from tenants.models import Business

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


@login_required
@hq_admin_required
def contract_template(request: HttpRequest) -> HttpResponse:
    """
    Show the contract template page with download link.
    """
    return render(
        request,
        "hq/contract_template.html",
        {
            "contracts_enabled": True,
            "active_tab": "contracts",
        },
    )


@login_required
@hq_admin_required
def contracts_list(request: HttpRequest) -> HttpResponse:
    """
    List all businesses with their contract status.
    Shows which businesses have signed contracts and which don't.
    """
    # Get filter params
    status_filter = request.GET.get("status", "all")  # all, signed, unsigned
    search_query = request.GET.get("q", "").strip()

    # Base queryset - use prefetch_related for ForeignKey relationship
    businesses = Business.objects.all().prefetch_related("contracts").order_by("-created_at")

    # Apply filters (using contracts relationship)
    if status_filter == "signed":
        businesses = businesses.filter(contracts__isnull=False).distinct()
    elif status_filter == "unsigned":
        businesses = businesses.filter(contracts__isnull=True)

    # Apply search
    if search_query:
        businesses = businesses.filter(Q(name__icontains=search_query) | Q(slug__icontains=search_query))

    # Pagination
    page_num = request.GET.get("page", 1)
    paginator = Paginator(businesses, 25)
    page_obj = paginator.get_page(page_num)

    # Build context with contract status
    businesses_with_status = []
    for biz in page_obj:
        # Get the most recent contract for this business (if any)
        latest_contract = biz.contracts.first() if hasattr(biz, "contracts") else None
        has_contract = latest_contract is not None

        businesses_with_status.append(
            {
                "business": biz,
                "has_contract": has_contract,
                "contract": latest_contract,
            }
        )

    return render(
        request,
        "hq/contracts_list.html",
        {
            "page_obj": page_obj,
            "businesses_with_status": businesses_with_status,
            "status_filter": status_filter,
            "search_query": search_query,
            "contracts_enabled": True,  # Always True since we're in the contracts module
            "active_tab": "contracts",
        },
    )


@login_required
@hq_admin_required
def contracts_detail(request: HttpRequest, business_id: int) -> HttpResponse:
    """
    View/upload contract for a specific business.
    Allows HQ to upload or replace a contract file.
    """
    business = get_object_or_404(Business, id=business_id)

    # Get the most recent contract for this business
    contract = business.contracts.first() if business.contracts.exists() else None

    if request.method == "POST":
        # Handle file upload
        uploaded_file = request.FILES.get("contract_file")
        notes = request.POST.get("notes", "").strip()

        if not uploaded_file:
            messages.error(request, "Please select a file to upload.")
            return redirect(request.path)

        # Validate file type
        if not uploaded_file.name.endswith(".pdf"):
            messages.error(request, "Only PDF files are allowed.")
            return redirect(request.path)

        # Validate file size (max 10MB)
        if uploaded_file.size > 10 * 1024 * 1024:
            messages.error(request, "File size must be less than 10MB.")
            return redirect(request.path)

        # Create or update contract
        if contract:
            # Update existing contract
            # Delete old file if exists
            if contract.file:
                contract.file.delete(save=False)
            contract.file = uploaded_file
            contract.notes = notes
            contract.uploaded_by = request.user
            contract.save()
            messages.success(request, f"Contract updated for {business.name}.")
        else:
            # Create new contract
            contract = MerchantContract.objects.create(
                business=business, file=uploaded_file, notes=notes, uploaded_by=request.user
            )
            messages.success(request, f"Contract uploaded for {business.name}.")

        # Log in audit if available
        try:
            from audit.models import AuditLog

            AuditLog.objects.create(
                business=business,
                user=request.user,
                action="UPLOAD_CONTRACT",
                resource_type="MerchantContract",
                resource_id=contract.id,
                details={
                    "business_id": business.id,
                    "business_name": business.name,
                    "file_name": uploaded_file.name,
                    "notes": notes,
                },
            )
        except Exception:
            pass  # Audit logging is optional

        return redirect("hq:contracts_list")

    # GET: Show upload form
    return render(
        request,
        "hq/contracts_detail.html",
        {
            "business": business,
            "contract": contract,
            "contracts_enabled": True,
            "active_tab": "contracts",
        },
    )


@login_required
@hq_admin_required
def contract_download(request: HttpRequest, contract_id: int) -> HttpResponse:
    """
    Download a contract file.
    """
    contract = get_object_or_404(MerchantContract, id=contract_id)

    # Check if file exists
    if not contract.file:
        messages.error(request, "Contract file not found.")
        return redirect("hq:contracts_list")

    try:
        # Return file as download
        response = FileResponse(contract.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{contract.business.slug}_contract.pdf"'

        # Log download in audit
        try:
            from audit.models import AuditLog

            AuditLog.objects.create(
                business=contract.business,
                user=request.user,
                action="DOWNLOAD_CONTRACT",
                resource_type="MerchantContract",
                resource_id=contract.id,
                details={
                    "business_id": contract.business.id,
                    "business_name": contract.business.name,
                },
            )
        except Exception:
            pass

        return response
    except Exception as e:
        messages.error(request, f"Error downloading contract: {str(e)}")
        return redirect("hq:contracts_list")


@login_required
@hq_admin_required
@require_POST
def contract_delete(request: HttpRequest, contract_id: int) -> HttpResponse:
    """
    Delete a contract (HQ only - for corrections/mistakes).
    """
    contract = get_object_or_404(MerchantContract, id=contract_id)
    business = contract.business

    # Log deletion before deleting
    try:
        from audit.models import AuditLog

        AuditLog.objects.create(
            business=business,
            user=request.user,
            action="DELETE_CONTRACT",
            resource_type="MerchantContract",
            resource_id=contract.id,
            details={
                "business_id": business.id,
                "business_name": business.name,
                "file_name": contract.file.name if contract.file else None,
                "notes": contract.notes,
            },
        )
    except Exception:
        pass

    # Delete file and contract record
    if contract.file:
        contract.file.delete(save=False)
    contract.delete()

    messages.success(request, f"Contract for {business.name} has been deleted.")
    return redirect("hq:contracts_list")


# ============================================================================
# HQ Staff Tour Guide
# ============================================================================


@login_required
@hq_admin_required
def staff_tour_guide(request: HttpRequest) -> HttpResponse:
    """
    Show the HQ staff tour guide page with PDF download link.
    """
    return render(
        request,
        "hq/staff_tour_guide.html",
        {
            "contracts_enabled": True,
            "active_tab": "staff_guide",
        },
    )


@login_required
@hq_admin_required
def staff_tour_guide_pdf(request: HttpRequest) -> HttpResponse:
    """
    Generate and download the HQ Staff Tour Guide as a PDF.

    Returns:
        HttpResponse with PDF attachment or error message.
    """
    # Check if ReportLab is available
    if not REPORTLAB_AVAILABLE:
        return HttpResponse(
            "PDF generation is not available. Please install reportlab.", status=503, content_type="text/plain"
        )

    try:
        # Create a BytesIO buffer for the PDF
        buffer = io.BytesIO()

        # Create the PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )

        # Container for the 'Flowable' objects
        elements = []

        # Define styles
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=colors.HexColor("#1e40af"),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        )

        heading_style = ParagraphStyle(
            "CustomHeading",
            parent=styles["Heading2"],
            fontSize=16,
            textColor=colors.HexColor("#1e40af"),
            spaceAfter=12,
            spaceBefore=12,
            fontName="Helvetica-Bold",
        )

        subheading_style = ParagraphStyle(
            "CustomSubHeading",
            parent=styles["Heading3"],
            fontSize=14,
            textColor=colors.HexColor("#374151"),
            spaceAfter=10,
            spaceBefore=10,
            fontName="Helvetica-Bold",
        )

        body_style = ParagraphStyle(
            "CustomBody",
            parent=styles["BodyText"],
            fontSize=11,
            leading=14,
            spaceAfter=10,
        )

        # Add title
        elements.append(Paragraph("Emajinet / Circuit City", title_style))
        elements.append(Paragraph("HQ Staff Tour Guide", title_style))
        elements.append(Spacer(1, 0.3 * inch))

        # Add introduction
        elements.append(Paragraph("Introduction", heading_style))
        intro_text = """
        Welcome to the Emajinet HQ Staff Tour Guide. This comprehensive document serves as your 
        reference for managing the Circuit City platform. As an HQ administrator, you have access 
        to powerful tools for supporting merchants, managing subscriptions, and ensuring smooth 
        operations across all businesses.
        """
        elements.append(Paragraph(intro_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Section 1: HQ Dashboard Overview
        elements.append(Paragraph("1. HQ Dashboard Overview", heading_style))

        elements.append(Paragraph("Key Metrics", subheading_style))
        dashboard_text = """
        The HQ Dashboard provides a real-time overview of platform activity:
        <br/><br/>
        • <b>Total Businesses:</b> Number of registered merchant accounts<br/>
        • <b>New Businesses (7d):</b> Recent sign-ups requiring onboarding attention<br/>
        • <b>Active Subscriptions:</b> Businesses with trial or paid plans<br/>
        • <b>MRR (Monthly Recurring Revenue):</b> Sum of all active subscription amounts<br/>
        • <b>Open Invoices:</b> Unpaid or past-due invoices requiring follow-up<br/>
        • <b>Agent Statistics:</b> Total agents and recent onboardings<br/>
        • <b>Stock Trends:</b> Inventory movement across all businesses
        """
        elements.append(Paragraph(dashboard_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Section 2: Business Management
        elements.append(Paragraph("2. Business Directory & Management", heading_style))

        business_text = """
        Access the Business Directory to view and manage all merchant accounts. You can:
        <br/><br/>
        • <b>Search:</b> Find businesses by name or slug<br/>
        • <b>View Details:</b> Access comprehensive business profiles including subscription history, 
        invoices, agents, and activity metrics<br/>
        • <b>Quick Actions:</b> Perform common tasks directly from the directory<br/>
        • <b>Filter:</b> Sort by date, status, or subscription tier
        """
        elements.append(Paragraph(business_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Section 3: Subscription Management
        elements.append(Paragraph("3. Subscription Management", heading_style))

        elements.append(Paragraph("Trial Extensions", subheading_style))
        trial_text = """
        You can extend trial periods for businesses that need more evaluation time:
        <br/><br/>
        • Navigate to Subscriptions list<br/>
        • Find the business subscription<br/>
        • Click "Extend Trial"<br/>
        • Enter number of days or specific end date<br/>
        • Confirm the extension
        <br/><br/>
        <b>Important:</b> Trials can only be extended before the first payment is received.
        """
        elements.append(Paragraph(trial_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        elements.append(Paragraph("Plan Changes", subheading_style))
        plan_text = """
        HQ can change subscription plans for businesses:
        <br/><br/>
        • <b>Starter:</b> Single location, no agents (K20,000/month)<br/>
        • <b>Pro:</b> Unlimited locations, up to 5 agents (K35,000/month)<br/>
        • <b>Pro Max:</b> Unlimited locations and agents (K50,000/month)
        <br/><br/>
        Use the "Set Plan" action to upgrade or downgrade as needed.
        """
        elements.append(Paragraph(plan_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        elements.append(Paragraph("Activation", subheading_style))
        activation_text = """
        To activate a trial subscription immediately (convert to paid):
        <br/><br/>
        • Select the subscription<br/>
        • Click "Activate Now"<br/>
        • A 30-day paid period begins immediately<br/>
        • Next billing date is set automatically
        """
        elements.append(Paragraph(activation_text, body_style))

        # Add page break
        elements.append(PageBreak())

        # Section 4: Invoice Management
        elements.append(Paragraph("4. Invoice & Payment Tracking", heading_style))

        invoice_text = """
        Monitor payment status and financial health through the Invoices section:
        <br/><br/>
        • <b>Open Invoices:</b> Awaiting payment - may require follow-up<br/>
        • <b>Past Due:</b> Overdue invoices requiring immediate attention<br/>
        • <b>Paid/Settled:</b> Completed transactions<br/>
        • <b>Refunds:</b> Process refunds or credit notes when necessary
        <br/><br/>
        <b>Refund Process:</b>
        <br/>
        1. Navigate to the invoice<br/>
        2. Click "Refund"<br/>
        3. A credit note is automatically generated<br/>
        4. The original invoice is linked to the refund for audit purposes
        """
        elements.append(Paragraph(invoice_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Section 5: Account Support
        elements.append(Paragraph("5. Account Support Tools", heading_style))

        support_text = """
        HQ staff have access to powerful support tools for assisting merchants:
        <br/><br/>
        <b>Password Reset:</b><br/>
        • Navigate to Business → Account Support<br/>
        • Select the user<br/>
        • Click "Reset Password"<br/>
        • A new temporary password is generated and can be shared securely
        <br/><br/>
        <b>Account Unlock:</b><br/>
        • If a user is locked out after failed login attempts<br/>
        • Use "Unlock Account" to restore access immediately
        <br/><br/>
        <b>Force Logout:</b><br/>
        • Terminate active sessions if suspicious activity is detected<br/>
        • User must log in again with valid credentials
        <br/><br/>
        <b>Session Management:</b><br/>
        • View all active sessions for a user<br/>
        • Review IP addresses and device information<br/>
        • Terminate individual sessions as needed
        """
        elements.append(Paragraph(support_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Section 6: Analytics
        elements.append(Paragraph("6. Analytics & Reporting", heading_style))

        analytics_text = """
        The HQ Analytics page provides deep insights into platform performance:
        <br/><br/>
        • <b>Filter by Business:</b> Focus on individual merchant metrics<br/>
        • <b>Filter by Vertical:</b> Compare performance across Phones, Clothing, Liquor, Pharmacy, Gym<br/>
        • <b>Date Ranges:</b> Analyze trends over custom time periods<br/>
        • <b>Top Agents:</b> Identify high performers across all businesses<br/>
        • <b>Revenue Trends:</b> Track sales and profit margins<br/>
        • <b>Inventory Insights:</b> Monitor stock turnover and sell-through rates
        """
        elements.append(Paragraph(analytics_text, body_style))

        # Add page break
        elements.append(PageBreak())

        # Section 7: Contract Management
        elements.append(Paragraph("7. Contract Management", heading_style))

        contract_text = """
        Manage merchant service agreements through the Contracts section:
        <br/><br/>
        • <b>Contract Template:</b> Download the standard merchant services agreement<br/>
        • <b>Upload Contracts:</b> Store signed agreements for each business<br/>
        • <b>Contract Status:</b> Track which businesses have signed contracts<br/>
        • <b>Download:</b> Retrieve contracts for review or audit purposes
        <br/><br/>
        <b>Best Practice:</b> Ensure all businesses on paid plans have signed contracts on file.
        """
        elements.append(Paragraph(contract_text, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Section 8: Troubleshooting
        elements.append(Paragraph("8. Common Troubleshooting", heading_style))

        elements.append(Paragraph("Issue: Merchant can't log in", subheading_style))
        troubleshoot1 = """
        1. Check if account is locked (failed login attempts)<br/>
        2. Use "Unlock Account" if locked<br/>
        3. Verify email address is correct<br/>
        4. Reset password if credentials are lost<br/>
        5. Check if 2FA/OTP is enabled and working
        """
        elements.append(Paragraph(troubleshoot1, body_style))
        elements.append(Spacer(1, 0.15 * inch))

        elements.append(Paragraph("Issue: Subscription not renewing", subheading_style))
        troubleshoot2 = """
        1. Check subscription status (should be ACTIVE)<br/>
        2. Verify next_billing_date is set<br/>
        3. Check for failed payment attempts<br/>
        4. Review business's invoice history<br/>
        5. Manually activate if payment is confirmed
        """
        elements.append(Paragraph(troubleshoot2, body_style))
        elements.append(Spacer(1, 0.15 * inch))

        elements.append(Paragraph("Issue: Agent limit reached", subheading_style))
        troubleshoot3 = """
        1. Check business's current plan (Starter = 0, Pro = 5, Pro Max = unlimited)<br/>
        2. Verify actual agent count in Agents section<br/>
        3. Upgrade plan if business needs more agents<br/>
        4. Remove inactive agents if at limit
        """
        elements.append(Paragraph(troubleshoot3, body_style))
        elements.append(Spacer(1, 0.2 * inch))

        # Section 9: Security & Best Practices
        elements.append(Paragraph("9. Security & Best Practices", heading_style))

        security_text = """
        As an HQ administrator, follow these guidelines:
        <br/><br/>
        • <b>Data Privacy:</b> Only access business data when necessary for support<br/>
        • <b>Password Resets:</b> Share temporary passwords through secure channels only<br/>
        • <b>Audit Trail:</b> All HQ actions are logged - maintain professional conduct<br/>
        • <b>Confidentiality:</b> Business data is confidential and should not be shared externally<br/>
        • <b>Escalation:</b> For complex issues, consult with senior HQ staff or technical team<br/>
        • <b>Documentation:</b> Record support interactions and resolutions for future reference
        """
        elements.append(Paragraph(security_text, body_style))
        elements.append(Spacer(1, 0.3 * inch))

        # Footer
        footer_text = """
        <br/><br/>
        <i>This guide is for HQ staff only. For questions or updates to this document, 
        contact the HQ team lead.</i>
        <br/><br/>
        <b>Document Version:</b> 1.0<br/>
        <b>Last Updated:</b> December 2025
        """
        elements.append(Paragraph(footer_text, body_style))

        # Build PDF
        doc.build(elements)

        # Get the PDF data from the buffer
        pdf_data = buffer.getvalue()
        buffer.close()

        # Create the HTTP response with PDF
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="hq_staff_tour_guide.pdf"'
        response.write(pdf_data)

        # Log download in audit if available
        try:
            from audit.utils import log_hq_action

            log_hq_action(
                request,
                action="DOWNLOAD_TOUR_GUIDE",
                entity_type="HQ_DOCUMENTATION",
                message="Downloaded HQ Staff Tour Guide PDF",
            )
        except Exception:
            pass  # Audit logging is optional

        return response

    except Exception as e:
        # Never 500 - return a friendly error
        import logging

        logger = logging.getLogger(__name__)
        logger.exception("Error generating HQ tour guide PDF")

        return HttpResponse(
            f"Unable to generate PDF at this time. Please contact support. (Error: {str(e)})",
            status=500,
            content_type="text/plain",
        )
