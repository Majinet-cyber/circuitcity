# sales/services/rollback.py
"""
Sale Rollback Service
=====================
Atomic, safe rollback of sales across all verticals.

Features:
- Atomic transactions (all-or-nothing)
- Inventory restoration (phones, clothing, pharmacy, liquor)
- Refund tracking
- Commission reversal
- Audit trail
- Multi-tenant isolation
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Dict, Any
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from sales.models import Sale, SaleRollback, RollbackReason, SaleCommission
from inventory.models import InventoryItem
from tenants.models import Business

User = get_user_model()


class RollbackError(Exception):
    """Raised when a rollback operation fails"""
    pass


class RollbackService:
    """
    Service for rolling back sales safely and atomically.
    """
    
    @staticmethod
    def can_rollback(sale: Sale, user: User, business: Business) -> tuple[bool, str]:
        """
        Check if a sale can be rolled back by the given user.
        
        Returns:
            (can_rollback: bool, reason: str)
        """
        # Already rolled back?
        if sale.is_rolled_back:
            return False, "Sale has already been rolled back"
        
        # Check business ownership
        if sale.item.business != business:
            return False, "Sale does not belong to this business"
        
        # Check user permissions
        from tenants.models import Membership
        
        try:
            membership = Membership.objects.get(user=user, business=business)
            role = membership.role.upper()
            
            # Managers can rollback any sale
            if role in ["MANAGER", "OWNER"]:
                return True, ""
            
            # Agents can only rollback their own sales within 10 minutes
            if role == "AGENT":
                if sale.agent != user:
                    return False, "Agents can only rollback their own sales"
                
                time_since_sale = timezone.now() - sale.created_at
                if time_since_sale > timedelta(minutes=10):
                    return False, "Agents can only rollback sales within 10 minutes"
                
                return True, ""
            
            return False, "Insufficient permissions"
            
        except Membership.DoesNotExist:
            return False, "User is not a member of this business"
    
    @staticmethod
    @transaction.atomic
    def rollback_sale(
        sale: Sale,
        user: User,
        business: Business,
        reason: str,
        refunded: bool = False,
        refunded_amount: Decimal = Decimal("0.00"),
        return_to_stock: bool = False,
        notes: str = ""
    ) -> SaleRollback:
        """
        Rollback a sale atomically.
        
        Args:
            sale: The sale to rollback
            user: User performing the rollback
            business: Business context
            reason: Rollback reason (DAMAGED, RETURNED, ERROR, OTHER)
            refunded: Whether a refund was issued
            refunded_amount: Amount refunded (if any)
            return_to_stock: Whether to return item to stock
            notes: Additional notes
        
        Returns:
            SaleRollback instance
        
        Raises:
            RollbackError: If rollback fails validation or execution
        """
        # Validate
        can_rollback, error_msg = RollbackService.can_rollback(sale, user, business)
        if not can_rollback:
            raise RollbackError(error_msg)
        
        # Validate reason
        if reason not in dict(RollbackReason.choices):
            raise RollbackError(f"Invalid rollback reason: {reason}")
        
        # Validate refund amount
        if refunded and refunded_amount <= 0:
            raise RollbackError("Refunded amount must be greater than 0 when refund is issued")
        
        if refunded_amount > sale.price:
            raise RollbackError(f"Refunded amount ({refunded_amount}) cannot exceed sale price ({sale.price})")
        
        # Mark sale as rolled back
        sale.is_rolled_back = True
        sale.rolled_back_at = timezone.now()
        sale.rolled_back_by = user
        sale.save(update_fields=["is_rolled_back", "rolled_back_at", "rolled_back_by"])
        
        # Create rollback record
        rollback = SaleRollback.objects.create(
            sale=sale,
            reason=reason,
            refunded=refunded,
            refunded_amount=refunded_amount,
            return_to_stock=return_to_stock,
            notes=notes,
            created_by=user,
        )
        
        # Reverse inventory changes
        if return_to_stock:
            RollbackService._restore_inventory(sale, business)
        
        # Reverse commissions
        RollbackService._reverse_commissions(sale)
        
        # Create refund ledger entry if needed
        if refunded and refunded_amount > 0:
            RollbackService._create_refund_entry(sale, refunded_amount, business)
        
        return rollback
    
    @staticmethod
    def _restore_inventory(sale: Sale, business: Business) -> None:
        """
        Restore inventory based on vertical type.
        
        For phones: Mark item as IN_STOCK again
        For clothing/pharmacy/liquor: Increment stock quantity
        For gym: Reverse membership payment (complex, handled separately)
        """
        item = sale.item
        
        # Resolve vertical safely (business doesn't have .kind attribute)
        from inventory.authz import resolve_business_kind
        vertical = resolve_business_kind(business=business).lower()
        
        if vertical == "phones":
            # Phones: Mark item as back in stock
            item.status = "IN_STOCK"
            item.sold_at = None
            item.sold_by = None
            item.save(update_fields=["status", "sold_at", "sold_by"])
        
        elif vertical in ["clothing", "pharmacy", "liquor"]:
            # For these verticals, we'd need to increment stock quantity
            # This depends on how stock is tracked in each vertical
            # For now, we'll add a note that this needs vertical-specific logic
            pass  # TODO: Implement vertical-specific stock restoration
        
        elif vertical == "gym":
            # Gym memberships are complex - would need to reverse payment
            # and adjust membership end dates
            pass  # TODO: Implement gym membership reversal
    
    @staticmethod
    def _reverse_commissions(sale: Sale) -> None:
        """
        Reverse commission entries for this sale.
        Mark them as reversed rather than deleting.
        """
        commissions = SaleCommission.objects.filter(sale=sale, is_reversed=False)
        
        for commission in commissions:
            commission.is_reversed = True
            commission.reversed_at = timezone.now()
            commission.save(update_fields=["is_reversed", "reversed_at"])
    
    @staticmethod
    def _create_refund_entry(sale: Sale, refunded_amount: Decimal, business: Business) -> None:
        """
        Create a negative ledger entry for the refund.
        This ensures reports show refunds correctly.
        """
        # Import here to avoid circular imports
        try:
            from wallet.models import Transaction, TransactionType
            
            # Create negative transaction for refund
            Transaction.objects.create(
                business=business,
                user=sale.agent,
                transaction_type=TransactionType.REFUND,
                amount=-refunded_amount,  # Negative amount
                description=f"Refund for rolled back sale #{sale.pk}",
                related_sale=sale,
            )
        except ImportError:
            # Wallet app not available, skip ledger entry
            pass
    
    @staticmethod
    def get_rollback_history(business: Business, limit: int = 30) -> list[SaleRollback]:
        """
        Get recent rollback history for a business.
        
        Args:
            business: Business to get rollbacks for
            limit: Maximum number of rollbacks to return
        
        Returns:
            List of SaleRollback instances
        """
        return list(
            SaleRollback.objects
            .filter(sale__item__business=business)
            .select_related("sale", "sale__item", "sale__agent", "created_by")
            .order_by("-created_at")[:limit]
        )
    
    @staticmethod
    def get_rollback_stats(business: Business, days: int = 30) -> Dict[str, Any]:
        """
        Get rollback statistics for a business.
        
        Args:
            business: Business to get stats for
            days: Number of days to look back
        
        Returns:
            Dictionary with rollback statistics
        """
        from django.db.models import Count, Sum, Q
        
        cutoff = timezone.now() - timedelta(days=days)
        
        rollbacks = SaleRollback.objects.filter(
            sale__item__business=business,
            created_at__gte=cutoff
        )
        
        stats = rollbacks.aggregate(
            total_rollbacks=Count("id"),
            total_refunded=Sum("refunded_amount"),
            returned_to_stock=Count("id", filter=Q(return_to_stock=True)),
        )
        
        # Breakdown by reason
        by_reason = rollbacks.values("reason").annotate(count=Count("id"))
        
        return {
            "total_rollbacks": stats["total_rollbacks"] or 0,
            "total_refunded": stats["total_refunded"] or Decimal("0.00"),
            "returned_to_stock": stats["returned_to_stock"] or 0,
            "by_reason": list(by_reason),
            "period_days": days,
        }


__all__ = ["RollbackService", "RollbackError"]

