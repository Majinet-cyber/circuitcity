# hq/views_contracts.py
"""
HQ views for managing merchant contracts.
"""
from __future__ import annotations

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


@login_required
@hq_admin_required
def contract_template(request: HttpRequest) -> HttpResponse:
    """
    Show the contract template page with download link.
    """
    return render(request, 'hq/contract_template.html')


@login_required
@hq_admin_required
def contracts_list(request: HttpRequest) -> HttpResponse:
    """
    List all businesses with their contract status.
    Shows which businesses have signed contracts and which don't.
    """
    # Get filter params
    status_filter = request.GET.get('status', 'all')  # all, signed, unsigned
    search_query = request.GET.get('q', '').strip()
    
    # Base queryset
    businesses = Business.objects.all().select_related('merchant_contract').order_by('-created_at')
    
    # Apply filters
    if status_filter == 'signed':
        businesses = businesses.filter(merchant_contract__isnull=False)
    elif status_filter == 'unsigned':
        businesses = businesses.filter(merchant_contract__isnull=True)
    
    # Apply search
    if search_query:
        businesses = businesses.filter(
            Q(name__icontains=search_query) |
            Q(slug__icontains=search_query)
        )
    
    # Pagination
    page_num = request.GET.get('page', 1)
    paginator = Paginator(businesses, 25)
    page_obj = paginator.get_page(page_num)
    
    # Build context with contract status
    businesses_with_status = []
    for biz in page_obj:
        has_contract = hasattr(biz, 'merchant_contract') and biz.merchant_contract is not None
        businesses_with_status.append({
            'business': biz,
            'has_contract': has_contract,
            'contract': biz.merchant_contract if has_contract else None,
        })
    
    return render(request, 'hq/contracts_list.html', {
        'page_obj': page_obj,
        'businesses_with_status': businesses_with_status,
        'status_filter': status_filter,
        'search_query': search_query,
    })


@login_required
@hq_admin_required
def contracts_detail(request: HttpRequest, business_id: int) -> HttpResponse:
    """
    View/upload contract for a specific business.
    Allows HQ to upload or replace a contract file.
    """
    business = get_object_or_404(Business, id=business_id)
    
    # Try to get existing contract
    try:
        contract = business.merchant_contract
    except MerchantContract.DoesNotExist:
        contract = None
    
    if request.method == 'POST':
        # Handle file upload
        uploaded_file = request.FILES.get('contract_file')
        notes = request.POST.get('notes', '').strip()
        
        if not uploaded_file:
            messages.error(request, "Please select a file to upload.")
            return redirect(request.path)
        
        # Validate file type
        if not uploaded_file.name.endswith('.pdf'):
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
                business=business,
                file=uploaded_file,
                notes=notes,
                uploaded_by=request.user
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
                    'business_id': business.id,
                    'business_name': business.name,
                    'file_name': uploaded_file.name,
                    'notes': notes,
                }
            )
        except Exception:
            pass  # Audit logging is optional
        
        return redirect('hq:contracts_list')
    
    # GET: Show upload form
    return render(request, 'hq/contracts_detail.html', {
        'business': business,
        'contract': contract,
    })


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
        return redirect('hq:contracts_list')
    
    try:
        # Return file as download
        response = FileResponse(contract.file.open('rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{contract.business.slug}_contract.pdf"'
        
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
                    'business_id': contract.business.id,
                    'business_name': contract.business.name,
                }
            )
        except Exception:
            pass
        
        return response
    except Exception as e:
        messages.error(request, f"Error downloading contract: {str(e)}")
        return redirect('hq:contracts_list')


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
                'business_id': business.id,
                'business_name': business.name,
                'file_name': contract.file.name if contract.file else None,
                'notes': contract.notes,
            }
        )
    except Exception:
        pass
    
    # Delete file and contract record
    if contract.file:
        contract.file.delete(save=False)
    contract.delete()
    
    messages.success(request, f"Contract for {business.name} has been deleted.")
    return redirect('hq:contracts_list')

