"""
Corrections Framework Views (Feb 2026)
=======================================

Generic, vertical-aware views for data corrections.

These views work for ANY vertical that has registered its entities
via the corrections registry.

Routes:
- /corrections/<vertical>/                           - Dashboard
- /corrections/<vertical>/batch/create/              - Create new batch
- /corrections/<vertical>/batch/<batch_id>/          - Batch detail
- /corrections/<vertical>/batch/<batch_id>/preview/  - Preview batch
- /corrections/<vertical>/batch/<batch_id>/apply/    - Apply batch
- /corrections/<vertical>/batch/<batch_id>/rollback/ - Rollback batch
- /corrections/<vertical>/entity/<entity_label>/     - List entities
- /corrections/<vertical>/audit/                     - Audit trail
"""
from __future__ import annotations

from typing import Any, Dict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST, require_http_methods

from core.decorators import manager_required
from tenants.utils import require_business
from corrections.models import CorrectionBatch, CorrectionItem, CorrectionAuditLog, CorrectionStatus
from corrections.registry import registry
from corrections.service import CorrectionService
from corrections.utils import get_tenant_scoped_queryset
from inventory.verticals.base import base_context
from tenants.utils import get_active_business


# =============================================================================
# DASHBOARD
# =============================================================================

@never_cache
@login_required
@require_business
@manager_required
def corrections_dashboard(request: HttpRequest, vertical: str) -> HttpResponse:
    """
    Main corrections dashboard for a vertical.
    
    Shows:
    - Recent batches
    - Quick stats
    - Link to create new batch
    - Link to browse entities for corrections
    """
    ctx = base_context(request)
    business = ctx.get("business")
    
    # Validate vertical is registered
    adapter = registry.get_adapter(vertical)
    if not adapter:
        messages.error(request, f'Vertical "{vertical}" is not registered for corrections.')
        return redirect('inventory:inventory_dashboard')
    
    # Get recent batches for this vertical
    batches = CorrectionBatch.objects.filter(
        business=business,
        vertical=vertical,
    ).select_related('created_by', 'applied_by').order_by('-created_at')[:20]
    
    # Get entities for this vertical
    entities = adapter.get_entities()
    entity_list = [
        {
            'label': entity_config.label,
            'entity_label': entity_label,
            'description': entity_config.description,
            'field_count': len(entity_config.fields),
        }
        for entity_label, entity_config in entities.items()
    ]
    
    # Quick stats
    total_batches = CorrectionBatch.objects.filter(business=business, vertical=vertical).count()
    applied_batches = CorrectionBatch.objects.filter(
        business=business,
        vertical=vertical,
        status=CorrectionStatus.APPLIED,
    ).count()
    pending_batches = CorrectionBatch.objects.filter(
        business=business,
        vertical=vertical,
        status__in=[CorrectionStatus.DRAFT, CorrectionStatus.PREVIEW],
    ).count()
    
    ctx.update({
        'page_title': f'Data Corrections - {adapter.vertical_label}',
        'hero_title': f'Data Corrections',
        'hero_blurb': f'Safely fix erroneous data in your {adapter.vertical_label} business with full audit trail.',
        'vertical': vertical,
        'vertical_label': adapter.vertical_label,
        'batches': batches,
        'entities': entity_list,
        'total_batches': total_batches,
        'applied_batches': applied_batches,
        'pending_batches': pending_batches,
        'show_warning_banner': True,
        'active_tab': 'data_correction',
    })
    
    return render(request, 'corrections/dashboard.html', ctx)


# =============================================================================
# ENTITY BROWSER (Find records to correct)
# =============================================================================

@never_cache
@login_required
@require_business
@manager_required
def browse_entity(request: HttpRequest, vertical: str, entity_label: str) -> HttpResponse:
    """
    Browse records for a specific entity to find items needing correction.
    
    Features:
    - Search by any field
    - Show potentially erroneous entries (from adapter.find_erroneous_entries)
    - Bulk select for batch creation
    """
    import logging
    logger = logging.getLogger(__name__)
    
    ctx = base_context(request)
    business = ctx.get("business")
    
    # Validate vertical and entity
    adapter = registry.get_adapter(vertical)
    if not adapter:
        logger.warning(
            f"Corrections: Unknown vertical '{vertical}' requested by user {request.user.id}",
            extra={'request_id': getattr(request, 'request_id', 'N/A')}
        )
        messages.error(request, f'Vertical "{vertical}" is not registered.')
        return redirect('inventory:inventory_dashboard')
    
    entity_config = adapter.get_entities().get(entity_label)
    if not entity_config:
        logger.warning(
            f"Corrections: Unknown entity '{entity_label}' for vertical '{vertical}' "
            f"requested by user {request.user.id}",
            extra={'request_id': getattr(request, 'request_id', 'N/A')}
        )
        messages.error(request, f'Entity "{entity_label}" not found in {vertical}.')
        return redirect('corrections:dashboard', vertical=vertical)
    
    # Get search parameters
    search_query = request.GET.get('q', '').strip()
    show_errors_only = request.GET.get('errors_only', '') == '1'
    page = request.GET.get('page', 1)
    
    # Get queryset (with defensive error handling)
    try:
        if show_errors_only:
            # Use adapter's find_erroneous_entries heuristic
            queryset = adapter.find_erroneous_entries(
                entity_label=entity_label,
                business=business,
                limit=100,
            )
        else:
            # Show all records for this entity (scoped to business)
            # Use business_filter_path to handle models with indirect business relation
            business_filter_key = entity_config.business_filter_path
            filter_kwargs = {business_filter_key: business}
            
            # Apply base filters (e.g., kind='pharmacy' for MerchProduct)
            if hasattr(entity_config, 'base_filters') and entity_config.base_filters:
                filter_kwargs.update(entity_config.base_filters)
            
            queryset = entity_config.model.objects.filter(**filter_kwargs)
            
            # Apply search if provided
            if search_query:
                # Build Q object for searching across text fields
                q_filter = Q()
                for field_name, field_config in entity_config.fields.items():
                    if field_config.field_type == 'string':
                        q_filter |= Q(**{f'{field_name}__icontains': search_query})
                
                if q_filter:
                    queryset = queryset.filter(q_filter)
            
            queryset = queryset.order_by('-id')[:200]
    except Exception as e:
        logger.error(
            f"Corrections: Failed to fetch {entity_label} records for {vertical}: {str(e)}",
            extra={'request_id': getattr(request, 'request_id', 'N/A')},
            exc_info=True
        )
        messages.error(
            request,
            f'Error loading {entity_config.label} records. Please contact support. '
            f'Reference: {getattr(request, "request_id", "N/A")}'
        )
        return redirect('corrections:dashboard', vertical=vertical)
    
    # Paginate
    paginator = Paginator(queryset, 25)
    try:
        records = paginator.page(page)
    except PageNotAnInteger:
        records = paginator.page(1)
    except EmptyPage:
        records = paginator.page(paginator.num_pages)
    
    ctx.update({
        'page_title': f'Correct {entity_config.label} - {adapter.vertical_label}',
        'hero_title': f'Correct {entity_config.label}',
        'hero_blurb': entity_config.description or f'Find and correct {entity_config.label} records',
        'vertical': vertical,
        'vertical_label': adapter.vertical_label,
        'entity_label': entity_label,
        'entity_config': entity_config,
        'records': records,
        'search_query': search_query,
        'show_errors_only': show_errors_only,
        'active_tab': 'data_correction',
    })
    
    return render(request, 'corrections/browse_entity.html', ctx)


# =============================================================================
# SINGLE RECORD EDIT
# =============================================================================

@never_cache
@login_required
@require_business
@manager_required
def edit_record(request: HttpRequest, vertical: str, entity_label: str, object_id: int) -> HttpResponse:
    """
    Edit a single record (creates a batch with one item).
    
    GET: Show edit form
    POST: Create batch + item, apply immediately
    """
    ctx = base_context(request)
    business = ctx.get("business")
    
    # Validate vertical and entity
    adapter = registry.get_adapter(vertical)
    if not adapter:
        messages.error(request, f'Vertical "{vertical}" is not registered.')
        return redirect('inventory:inventory_dashboard')
    
    entity_config = adapter.get_entities().get(entity_label)
    if not entity_config:
        messages.error(request, f'Entity "{entity_label}" not found.')
        return redirect('corrections:dashboard', vertical=vertical)
    
    # Get the record (tenant-scoped using entity's business_filter_path)
    queryset = get_tenant_scoped_queryset(
        model=entity_config.model,
        entity_config=entity_config,
        business=business,
        queryset=entity_config.model.objects.select_related(),
    )
    obj = get_object_or_404(queryset, pk=object_id)
    
    if request.method == 'POST':
        return _handle_edit_post(request, vertical, entity_label, object_id, adapter, entity_config, obj, ctx)
    
    # GET: Show form
    # Get correction history for this object
    history = CorrectionItem.objects.filter(
        batch__business=business,
        entity_label=entity_label,
        object_id=object_id,
    ).select_related('batch', 'batch__created_by').order_by('-batch__created_at')[:10]
    
    ctx.update({
        'page_title': f'Edit {entity_config.label} #{object_id}',
        'hero_title': f'Edit {entity_config.label}',
        'vertical': vertical,
        'vertical_label': adapter.vertical_label,
        'entity_label': entity_label,
        'entity_config': entity_config,
        'obj': obj,
        'history': history,
        'active_tab': 'data_correction',
    })
    
    return render(request, 'corrections/edit_record.html', ctx)


def _handle_edit_post(
    request: HttpRequest,
    vertical: str,
    entity_label: str,
    object_id: int,
    adapter,
    entity_config,
    obj,
    ctx: Dict[str, Any],
) -> HttpResponse:
    """Handle POST for single record edit."""
    business = ctx.get("business")
    
    # Get reason
    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Reason is required.')
        return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)
    
    # Initialize service
    service = CorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    # Create batch
    batch_result = service.create_batch(
        vertical=vertical,
        reason=reason,
        notes=f'Single record correction for {entity_label} #{object_id}',
    )
    
    if not batch_result.success:
        messages.error(request, batch_result.message)
        return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)
    
    batch = batch_result.batch
    
    # Collect changed fields
    items = []
    for field_name, field_config in entity_config.fields.items():
        new_value_raw = request.POST.get(field_name, '').strip()
        if not new_value_raw and not field_config.required:
            continue
        
        old_value = getattr(obj, field_name)
        
        # Coerce new value
        try:
            new_value = field_config.coerce(new_value_raw)
        except Exception as e:
            messages.error(request, f'Invalid {field_config.label}: {str(e)}')
            continue
        
        # Check if changed
        if str(old_value) != str(new_value):
            items.append({
                'entity_label': entity_label,
                'object_id': object_id,
                'field_name': field_name,
                'new_value': new_value,
            })
    
    if not items:
        messages.info(request, 'No changes detected.')
        return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)
    
    # Add items to batch
    add_result = service.add_items(batch=batch, items=items)
    if not add_result.success:
        messages.error(request, add_result.message)
        return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)
    
    # Apply immediately (single record edit)
    apply_result = service.apply_batch(batch)
    if apply_result.success:
        messages.success(request, f'Successfully corrected {len(items)} field(s).')
        return redirect('corrections:browse_entity', vertical=vertical, entity_label=entity_label)
    else:
        messages.error(request, f'Failed to apply corrections: {apply_result.message}')
        return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)


# =============================================================================
# BATCH OPERATIONS
# =============================================================================

@never_cache
@login_required
@require_business
@manager_required
def batch_detail(request: HttpRequest, vertical: str, batch_id: int) -> HttpResponse:
    """Show details of a correction batch."""
    ctx = base_context(request)
    business = ctx.get("business")
    
    batch = get_object_or_404(
        CorrectionBatch.objects.select_related('created_by', 'applied_by', 'rolled_back_by'),
        pk=batch_id,
        business=business,
        vertical=vertical,
    )
    
    items = batch.items.select_related().order_by('id')
    
    # Get adapter for vertical label
    adapter = registry.get_adapter(vertical)
    vertical_label = adapter.vertical_label if adapter else vertical.title()
    
    ctx.update({
        'page_title': f'Batch #{batch.pk} - {vertical_label}',
        'hero_title': f'Correction Batch #{batch.pk}',
        'vertical': vertical,
        'vertical_label': vertical_label,
        'batch': batch,
        'items': items,
        'active_tab': 'data_correction',
    })
    
    return render(request, 'corrections/batch_detail.html', ctx)


@csrf_protect
@require_POST
@login_required
@require_business
@manager_required
def batch_apply(request: HttpRequest, vertical: str, batch_id: int) -> HttpResponse:
    """Apply a correction batch."""
    ctx = base_context(request)
    business = ctx.get("business")
    
    batch = get_object_or_404(
        CorrectionBatch,
        pk=batch_id,
        business=business,
        vertical=vertical,
    )
    
    service = CorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    result = service.apply_batch(batch)
    
    if result.success:
        messages.success(request, result.message)
    else:
        messages.error(request, result.message)
        if result.errors:
            for error in result.errors[:5]:  # Show first 5 errors
                messages.warning(request, error)
    
    return redirect('corrections:batch_detail', vertical=vertical, batch_id=batch_id)


@csrf_protect
@require_POST
@login_required
@require_business
@manager_required
def batch_rollback(request: HttpRequest, vertical: str, batch_id: int) -> HttpResponse:
    """Rollback a correction batch."""
    ctx = base_context(request)
    business = ctx.get("business")
    
    batch = get_object_or_404(
        CorrectionBatch,
        pk=batch_id,
        business=business,
        vertical=vertical,
    )
    
    service = CorrectionService(
        business=business,
        user=request.user,
        request=request,
    )
    
    result = service.rollback_batch(batch)
    
    if result.success:
        messages.success(request, result.message)
    else:
        messages.error(request, result.message)
    
    return redirect('corrections:batch_detail', vertical=vertical, batch_id=batch_id)


# =============================================================================
# AUDIT TRAIL
# =============================================================================

@never_cache
@login_required
@require_business
@manager_required
def audit_trail(request: HttpRequest, vertical: str) -> HttpResponse:
    """Show audit trail for a vertical."""
    ctx = base_context(request)
    business = ctx.get("business")
    
    logs = CorrectionAuditLog.objects.filter(
        business=business,
        batch__vertical=vertical,
    ).select_related('performed_by', 'batch').order_by('-performed_at')[:100]
    
    # Get adapter for vertical label
    adapter = registry.get_adapter(vertical)
    vertical_label = adapter.vertical_label if adapter else vertical.title()
    
    ctx.update({
        'page_title': f'Audit Trail - {vertical_label}',
        'hero_title': 'Correction Audit Trail',
        'hero_blurb': f'Complete history of all corrections in {vertical_label}',
        'vertical': vertical,
        'vertical_label': vertical_label,
        'logs': logs,
        'active_tab': 'data_correction',
    })
    
    return render(request, 'corrections/audit_trail.html', ctx)


# =============================================================================
# RECORD DELETION (for duplicates/errors)
# =============================================================================

@csrf_protect
@require_POST
@login_required
@require_business
def delete_record(request: HttpRequest, vertical: str, entity_label: str, object_id: int) -> HttpResponse:
    """
    Delete a single record (for duplicates or errors).
    
    IMPORTANT: This delete path is intentionally hard-delete and unguarded.
    It exists to allow rapid correction of duplicate gym payments.
    Do not add role checks or soft-delete here.
    
    This is a destructive action that:
    1. HARD-deletes the record (permanently removes from database)
    2. Reverses any related effects (wallet entries, ledger, etc.)
    3. Logs the action with full audit trail
    
    Requires:
    - POST with reason and optional notes
    - Tenant isolation (record must belong to current business)
    - Any logged-in user with business access can delete
    """
    import logging
    logger = logging.getLogger(__name__)
    
    ctx = base_context(request)
    business = ctx.get("business")
    
    # Validate vertical and entity
    adapter = registry.get_adapter(vertical)
    if not adapter:
        messages.error(request, f'Vertical "{vertical}" is not registered.')
        return redirect('inventory:inventory_dashboard')
    
    entity_config = adapter.get_entities().get(entity_label)
    if not entity_config:
        messages.error(request, f'Entity "{entity_label}" not found.')
        return redirect('corrections:dashboard', vertical=vertical)
    
    # Get the record (tenant-scoped)
    queryset = get_tenant_scoped_queryset(
        model=entity_config.model,
        entity_config=entity_config,
        business=business,
    )
    obj = get_object_or_404(queryset, pk=object_id)
    
    # Get reason and notes
    reason = request.POST.get('reason', '').strip()
    notes = request.POST.get('notes', '').strip()
    
    if not reason:
        messages.error(request, 'Deletion reason is required.')
        return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)
    
    # Perform deletion based on entity type
    if entity_label == 'gym_payment':
        from corrections.services_deletion import GymPaymentDeletionService
        
        service = GymPaymentDeletionService(business=business, user=request.user)
        result = service.delete_payment(
            payment=obj,
            reason=reason,
            notes=notes,
            hard_delete=True,  # Hard delete for immediate duplicate removal (correctness > ceremony)
        )
        
        if result.success:
            messages.success(
                request,
                f'{entity_config.label} #{object_id} deleted successfully. '
                f'{result.wallet_entries_removed} wallet entries removed.'
            )
            logger.info(
                f"User {request.user.id} deleted {entity_label} #{object_id} "
                f"(reason: {reason})",
                extra={
                    'user_id': request.user.id,
                    'business_id': business.id,
                    'entity_label': entity_label,
                    'object_id': object_id,
                    'reason': reason,
                }
            )
            return redirect('corrections:browse_entity', vertical=vertical, entity_label=entity_label)
        else:
            messages.error(request, f'Failed to delete: {result.message}')
            for error in result.errors[:3]:  # Show first 3 errors
                messages.warning(request, error)
            return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)

    elif entity_label == 'pharmacy_sale':
        return _delete_pharmacy_sale(
            request=request,
            vertical=vertical,
            entity_label=entity_label,
            entity_config=entity_config,
            obj=obj,
            object_id=object_id,
            business=business,
            reason=reason,
            notes=notes,
            logger=logger,
        )

    else:
        # Entity type doesn't support deletion yet
        messages.error(
            request,
            f'Deletion is not yet supported for {entity_config.label}. '
            f'Please contact support if you need to remove this record.'
        )
        return redirect('corrections:edit_record', vertical=vertical, entity_label=entity_label, object_id=object_id)


def _delete_pharmacy_sale(
    request: HttpRequest,
    vertical: str,
    entity_label: str,
    entity_config,
    obj,
    object_id: int,
    business,
    reason: str,
    notes: str,
    logger,
) -> HttpResponse:
    """
    Soft-delete a PharmacySale record.

    Actions:
    1. Marks sale as is_deleted=True (soft delete — not removed from DB).
    2. Restores batch stock (batch.quantity += sale.quantity).
    3. Logs correction audit entry via CorrectionAuditLog.
    4. Also logs to audit.utils.log_audit if available.
    """
    from django.db import transaction as db_transaction
    from django.utils import timezone as tz

    try:
        with db_transaction.atomic():
            batch = obj.batch
            qty = obj.quantity

            # Soft-delete the sale
            obj.is_deleted = True
            obj.deleted_at = tz.now()
            obj.deleted_by = request.user
            obj.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

            # Restore batch stock
            batch.quantity = (batch.quantity or 0) + qty
            batch.save(update_fields=['quantity'])

            # Log to CorrectionAuditLog via convenience classmethod (best-effort)
            try:
                correction_batch = CorrectionBatch.objects.create(
                    business=business,
                    vertical=vertical,
                    status=CorrectionStatus.APPLIED,
                    created_by=request.user,
                    applied_by=request.user,
                    applied_at=tz.now(),
                    reason=reason,
                    notes=notes or f'Soft-deleted PharmacySale #{object_id} via data correction',
                )
                CorrectionAuditLog.log_action(
                    business=business,
                    performed_by=request.user,
                    action='pharmacy_sale_deleted',
                    details={
                        'entity_label': entity_label,
                        'object_id': object_id,
                        'reason': reason,
                        'notes': notes,
                        'qty_restored': qty,
                        'batch_id': batch.pk,
                    },
                    batch=correction_batch,
                    request=request,
                )
            except Exception as audit_err:
                logger.warning(
                    f'CorrectionAuditLog creation failed for pharmacy_sale #{object_id}: {audit_err}'
                )

            # Also log to audit app if available
            try:
                from audit.utils import log_audit
                log_audit(
                    request=request,
                    action='DELETE_PHARMACY_SALE',
                    entity='PharmacySale',
                    entity_id=str(object_id),
                    message=(
                        f'Sale #{object_id} soft-deleted via data correction. '
                        f'Reason: {reason}. Batch stock +{qty} restored.'
                    ),
                )
            except Exception:
                pass

        messages.success(
            request,
            f'Sale #{object_id} has been deleted and {qty} unit(s) returned to batch stock.',
        )
        logger.info(
            f"User {request.user.id} soft-deleted PharmacySale #{object_id} (reason: {reason})",
            extra={
                'user_id': request.user.id,
                'business_id': business.id,
                'entity_label': entity_label,
                'object_id': object_id,
                'reason': reason,
            },
        )
        return redirect('corrections:browse_entity', vertical=vertical, entity_label=entity_label)

    except Exception as exc:
        logger.error(
            f"Failed to delete PharmacySale #{object_id}: {exc}",
            exc_info=True,
            extra={'user_id': request.user.id, 'business_id': business.id},
        )
        messages.error(request, f'Failed to delete sale #{object_id}: {exc}')
        return redirect(
            'corrections:edit_record',
            vertical=vertical,
            entity_label=entity_label,
            object_id=object_id,
        )


# Export views
__all__ = [
    'corrections_dashboard',
    'browse_entity',
    'edit_record',
    'delete_record',
    'batch_detail',
    'batch_apply',
    'batch_rollback',
    'audit_trail',
]

