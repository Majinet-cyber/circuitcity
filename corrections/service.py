"""
Correction Service Layer (Feb 2026)
====================================

Business logic for managing correction batches:
- Preview: Calculate impact without committing
- Apply: Apply all corrections in a batch (transactional)
- Rollback: Restore original values if correction was wrong

Design:
- All operations are transactional (atomic)
- Full audit trail for every action
- Vertical-agnostic (uses registry)
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from tenants.models import Business
from corrections.models import (
    CorrectionBatch,
    CorrectionItem,
    CorrectionAuditLog,
    CorrectionStatus,
)
from corrections.registry import registry


@dataclass
class CorrectionResult:
    """Result of a correction operation."""
    
    success: bool
    message: str
    batch: Optional[CorrectionBatch] = None
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class CorrectionService:
    """
    Service class for handling data corrections.
    
    Workflow:
    1. create_batch() - Create a new batch
    2. add_items() - Add correction items to batch
    3. preview_batch() - Calculate impact (no commit)
    4. apply_batch() - Apply all corrections (atomic transaction)
    5. rollback_batch() - Restore original values (if needed)
    """
    
    def __init__(self, business: Business, user, request=None):
        """
        Initialize the service.
        
        Args:
            business: Business context
            user: User performing corrections (must be manager)
            request: Optional HTTP request for audit metadata
        """
        self.business = business
        self.user = user
        self.request = request
        
        # Validate manager permission
        self._validate_manager_permission()
    
    def _validate_manager_permission(self):
        """Ensure the user has manager permissions."""
        from core.roles import is_manager
        
        if not is_manager(self.user):
            raise PermissionDenied('Only managers can perform data corrections.')
    
    # ==========================================================================
    # BATCH MANAGEMENT
    # ==========================================================================
    
    def create_batch(
        self,
        vertical: str,
        reason: str,
        notes: str = '',
    ) -> CorrectionResult:
        """
        Create a new correction batch.
        
        Args:
            vertical: Vertical key (phones, clothing, gym, etc.)
            reason: Required reason for corrections
            notes: Optional notes
        
        Returns:
            CorrectionResult with created batch
        """
        if not reason or not reason.strip():
            return CorrectionResult(
                success=False,
                message='Reason is required.',
                errors=['Reason is required'],
            )
        
        # Validate vertical is registered
        adapter = registry.get_adapter(vertical)
        if not adapter:
            return CorrectionResult(
                success=False,
                message=f'Vertical "{vertical}" is not registered.',
                errors=[f'Unknown vertical: {vertical}'],
            )
        
        try:
            with transaction.atomic():
                # Create batch
                batch = CorrectionBatch.objects.create(
                    business=self.business,
                    vertical=vertical,
                    status=CorrectionStatus.DRAFT,
                    created_by=self.user,
                    reason=reason.strip(),
                    notes=notes.strip(),
                )
                
                # Audit log
                CorrectionAuditLog.log_action(
                    business=self.business,
                    performed_by=self.user,
                    action='batch_created',
                    details={
                        'batch_id': batch.pk,
                        'vertical': vertical,
                        'reason': reason.strip(),
                    },
                    batch=batch,
                    request=self.request,
                )
                
                return CorrectionResult(
                    success=True,
                    message=f'Correction batch created successfully.',
                    batch=batch,
                )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f'Failed to create batch: {str(e)}',
                errors=[str(e)],
            )
    
    def add_items(
        self,
        batch: CorrectionBatch,
        items: List[Dict[str, Any]],
    ) -> CorrectionResult:
        """
        Add correction items to a batch.
        
        Args:
            batch: CorrectionBatch instance
            items: List of dicts with keys:
                - entity_label: str
                - object_id: int
                - field_name: str
                - new_value: Any
        
        Returns:
            CorrectionResult
        """
        if batch.status not in (CorrectionStatus.DRAFT, CorrectionStatus.PREVIEW):
            return CorrectionResult(
                success=False,
                message='Cannot add items to a batch that has been applied or rolled back.',
                errors=['Batch is not in draft/preview state'],
            )
        
        # Get vertical adapter
        adapter = registry.get_adapter(batch.vertical)
        if not adapter:
            return CorrectionResult(
                success=False,
                message=f'Vertical "{batch.vertical}" not registered.',
                errors=['Vertical not found'],
            )
        
        errors = []
        added_count = 0
        
        try:
            with transaction.atomic():
                for idx, item_data in enumerate(items):
                    entity_label = item_data.get('entity_label')
                    object_id = item_data.get('object_id')
                    field_name = item_data.get('field_name')
                    new_value = item_data.get('new_value')
                    
                    # Validate entity
                    entity_config = adapter.get_entities().get(entity_label)
                    if not entity_config:
                        errors.append(f'Item {idx}: Unknown entity "{entity_label}"')
                        continue
                    
                    # Validate field
                    field_config = entity_config.get_field(field_name)
                    if not field_config:
                        errors.append(f'Item {idx}: Unknown field "{field_name}" for entity "{entity_label}"')
                        continue
                    
                    # Get object
                    try:
                        obj = entity_config.model.objects.get(
                            pk=object_id,
                            business=self.business,
                        )
                    except entity_config.model.DoesNotExist:
                        errors.append(f'Item {idx}: Object {entity_label}#{object_id} not found')
                        continue
                    
                    # Get old value
                    old_value = getattr(obj, field_name)
                    
                    # Coerce new value
                    try:
                        coerced_value = field_config.coerce(new_value)
                    except Exception as e:
                        errors.append(f'Item {idx}: Failed to coerce value: {str(e)}')
                        continue
                    
                    # Validate new value
                    is_valid, error_msg = field_config.validate(coerced_value)
                    if not is_valid:
                        errors.append(f'Item {idx}: {error_msg}')
                        continue
                    
                    # Calculate impact
                    impact = adapter.calculate_impact(
                        entity_label=entity_label,
                        obj=obj,
                        field_name=field_name,
                        old_value=old_value,
                        new_value=coerced_value,
                    )
                    
                    # Create correction item
                    CorrectionItem.objects.create(
                        batch=batch,
                        entity_label=entity_label,
                        model_name=f'{entity_config.model._meta.app_label}.{entity_config.model._meta.model_name}',
                        object_id=object_id,
                        field_name=field_name,
                        old_value=self._serialize_value(old_value),
                        new_value=self._serialize_value(coerced_value),
                        revenue_impact=impact.get('revenue_impact'),
                        profit_impact=impact.get('profit_impact'),
                    )
                    
                    added_count += 1
                
                # Recalculate batch metrics
                batch.recalculate_metrics()
                
                # Audit log
                CorrectionAuditLog.log_action(
                    business=self.business,
                    performed_by=self.user,
                    action='items_added',
                    details={
                        'batch_id': batch.pk,
                        'items_added': added_count,
                        'errors_count': len(errors),
                    },
                    batch=batch,
                    request=self.request,
                )
                
                if errors:
                    return CorrectionResult(
                        success=True,
                        message=f'Added {added_count} items with {len(errors)} errors.',
                        batch=batch,
                        errors=errors,
                    )
                else:
                    return CorrectionResult(
                        success=True,
                        message=f'Added {added_count} items successfully.',
                        batch=batch,
                    )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f'Failed to add items: {str(e)}',
                errors=[str(e)],
            )
    
    # ==========================================================================
    # PREVIEW / APPLY / ROLLBACK
    # ==========================================================================
    
    def preview_batch(self, batch: CorrectionBatch) -> CorrectionResult:
        """
        Preview a batch (calculate impact, no commit).
        
        Args:
            batch: CorrectionBatch instance
        
        Returns:
            CorrectionResult with preview details
        """
        if not batch.can_be_applied():
            return CorrectionResult(
                success=False,
                message='Batch cannot be previewed (already applied or rolled back).',
                errors=['Invalid batch status'],
            )
        
        try:
            # Update batch status to PREVIEW
            batch.status = CorrectionStatus.PREVIEW
            batch.save(update_fields=['status'])
            
            # Audit log
            CorrectionAuditLog.log_action(
                business=self.business,
                performed_by=self.user,
                action='batch_previewed',
                details={
                    'batch_id': batch.pk,
                    'items_count': batch.items_count,
                    'revenue_impact': float(batch.revenue_impact),
                    'profit_impact': float(batch.profit_impact),
                },
                batch=batch,
                request=self.request,
            )
            
            return CorrectionResult(
                success=True,
                message=f'Preview complete: {batch.items_count} items, '
                        f'Revenue impact: {batch.revenue_impact}, '
                        f'Profit impact: {batch.profit_impact}',
                batch=batch,
            )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f'Preview failed: {str(e)}',
                errors=[str(e)],
            )
    
    def apply_batch(self, batch: CorrectionBatch) -> CorrectionResult:
        """
        Apply all corrections in a batch (transactional).
        
        Args:
            batch: CorrectionBatch instance
        
        Returns:
            CorrectionResult
        """
        if not batch.can_be_applied():
            return CorrectionResult(
                success=False,
                message='Batch cannot be applied (invalid status).',
                errors=['Batch already applied or rolled back'],
            )
        
        adapter = registry.get_adapter(batch.vertical)
        if not adapter:
            return CorrectionResult(
                success=False,
                message=f'Vertical "{batch.vertical}" not registered.',
                errors=['Vertical not found'],
            )
        
        applied_count = 0
        failed_count = 0
        errors = []
        
        try:
            with transaction.atomic():
                items = batch.items.filter(applied_at__isnull=True)
                
                for item in items:
                    try:
                        # Get entity config
                        entity_config = adapter.get_entities().get(item.entity_label)
                        if not entity_config:
                            raise ValueError(f'Unknown entity: {item.entity_label}')
                        
                        # Get object
                        obj = entity_config.model.objects.select_for_update().get(
                            pk=item.object_id,
                            business=self.business,
                        )
                        
                        # Store old value for hook
                        old_value = self._deserialize_value(item.old_value)
                        new_value = self._deserialize_value(item.new_value)
                        
                        # Apply correction
                        setattr(obj, item.field_name, new_value)
                        obj.save(update_fields=[item.field_name, 'updated_at'])
                        
                        # Call post-correction hook (for recompute, validation, etc.)
                        adapter.post_correction_hook(
                            entity_label=item.entity_label,
                            obj=obj,
                            field_name=item.field_name,
                            old_value=old_value,
                            new_value=new_value,
                        )
                        
                        # Mark item as applied
                        item.applied_at = timezone.now()
                        item.save(update_fields=['applied_at'])
                        
                        applied_count += 1
                        
                    except Exception as e:
                        item.error = str(e)
                        item.save(update_fields=['error'])
                        failed_count += 1
                        errors.append(f'Item {item.pk}: {str(e)}')
                
                # Update batch status
                batch.status = CorrectionStatus.APPLIED
                batch.applied_by = self.user
                batch.applied_at = timezone.now()
                batch.recalculate_metrics()
                batch.save(update_fields=['status', 'applied_by', 'applied_at'])
                
                # Audit log
                CorrectionAuditLog.log_action(
                    business=self.business,
                    performed_by=self.user,
                    action='batch_applied',
                    details={
                        'batch_id': batch.pk,
                        'applied_count': applied_count,
                        'failed_count': failed_count,
                    },
                    batch=batch,
                    request=self.request,
                )
                
                if failed_count > 0:
                    return CorrectionResult(
                        success=True,
                        message=f'Applied {applied_count} items, {failed_count} failed.',
                        batch=batch,
                        errors=errors,
                    )
                else:
                    return CorrectionResult(
                        success=True,
                        message=f'Successfully applied all {applied_count} corrections.',
                        batch=batch,
                    )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f'Failed to apply batch: {str(e)}',
                errors=[str(e)],
            )
    
    def rollback_batch(self, batch: CorrectionBatch) -> CorrectionResult:
        """
        Rollback a batch (restore original values).
        
        Args:
            batch: CorrectionBatch instance
        
        Returns:
            CorrectionResult
        """
        if not batch.can_be_rolled_back():
            return CorrectionResult(
                success=False,
                message='Batch cannot be rolled back (not applied yet).',
                errors=['Batch not in applied state'],
            )
        
        adapter = registry.get_adapter(batch.vertical)
        if not adapter:
            return CorrectionResult(
                success=False,
                message=f'Vertical "{batch.vertical}" not registered.',
                errors=['Vertical not found'],
            )
        
        rolled_back_count = 0
        failed_count = 0
        errors = []
        
        try:
            with transaction.atomic():
                items = batch.items.filter(applied_at__isnull=False, rolled_back_at__isnull=True)
                
                for item in items:
                    try:
                        # Get entity config
                        entity_config = adapter.get_entities().get(item.entity_label)
                        if not entity_config:
                            raise ValueError(f'Unknown entity: {item.entity_label}')
                        
                        # Get object
                        obj = entity_config.model.objects.select_for_update().get(
                            pk=item.object_id,
                            business=self.business,
                        )
                        
                        # Restore old value
                        setattr(obj, item.field_name, self._deserialize_value(item.old_value))
                        obj.save(update_fields=[item.field_name, 'updated_at'])
                        
                        # Mark item as rolled back
                        item.rolled_back_at = timezone.now()
                        item.save(update_fields=['rolled_back_at'])
                        
                        rolled_back_count += 1
                        
                    except Exception as e:
                        failed_count += 1
                        errors.append(f'Item {item.pk}: {str(e)}')
                
                # Update batch status
                batch.status = CorrectionStatus.ROLLED_BACK
                batch.rolled_back_by = self.user
                batch.rolled_back_at = timezone.now()
                batch.save(update_fields=['status', 'rolled_back_by', 'rolled_back_at'])
                
                # Audit log
                CorrectionAuditLog.log_action(
                    business=self.business,
                    performed_by=self.user,
                    action='batch_rolled_back',
                    details={
                        'batch_id': batch.pk,
                        'rolled_back_count': rolled_back_count,
                        'failed_count': failed_count,
                    },
                    batch=batch,
                    request=self.request,
                )
                
                if failed_count > 0:
                    return CorrectionResult(
                        success=True,
                        message=f'Rolled back {rolled_back_count} items, {failed_count} failed.',
                        batch=batch,
                        errors=errors,
                    )
                else:
                    return CorrectionResult(
                        success=True,
                        message=f'Successfully rolled back all {rolled_back_count} corrections.',
                        batch=batch,
                    )
        
        except Exception as e:
            return CorrectionResult(
                success=False,
                message=f'Failed to rollback batch: {str(e)}',
                errors=[str(e)],
            )
    
    # ==========================================================================
    # HELPERS
    # ==========================================================================
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value for JSON storage."""
        if isinstance(value, Decimal):
            return str(value)
        elif hasattr(value, 'isoformat'):
            return value.isoformat()
        elif hasattr(value, 'pk'):
            return value.pk
        return value
    
    def _deserialize_value(self, value: Any) -> Any:
        """Deserialize a value from JSON storage."""
        # Note: Type coercion happens in FieldConfig.coerce()
        # This is just a simple passthrough for now
        return value


# Export
__all__ = [
    'CorrectionResult',
    'CorrectionService',
]

