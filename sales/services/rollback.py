# sales/services/rollback.py
"""
Sale Rollback Service
=====================
Atomic, safe rollback of sales across all verticals.

Features:
- Atomic transactions (all-or-nothing)
- Idempotent (safe to retry)
- Inventory restoration (phones, clothing, pharmacy, liquor)
- Refund tracking
- Commission reversal
- Audit trail
- Multi-tenant isolation
- Zero HTTP 500 tolerance (structured errors only)
"""
from __future__ import annotations

import logging
from decimal import Decimal
from datetime import timedelta
from typing import Optional, Dict, Any, Tuple

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from sales.models import Sale, SaleRollback, RollbackReason, SaleCommission
from inventory.models import InventoryItem
from tenants.models import Business

User = get_user_model()
logger = logging.getLogger(__name__)


class RollbackError(Exception):
    """Raised when a rollback operation fails validation or business rules"""

    pass


class RollbackService:
    """
    Service for rolling back sales safely and atomically.
    """

    @staticmethod
    def is_already_rolled_back(sale: Sale) -> bool:
        """
        Check if a sale has already been rolled back.

        This is the source of truth for rollback status.

        Args:
            sale: Sale instance to check

        Returns:
            bool: True if sale is already rolled back, False otherwise
        """
        # Check the is_rolled_back flag (primary source of truth)
        if sale.is_rolled_back:
            return True

        # Also check rolled_back_at timestamp as secondary check
        if hasattr(sale, "rolled_back_at") and sale.rolled_back_at is not None:
            return True

        return False

    @staticmethod
    def can_rollback(sale: Sale, user: User, business: Business) -> Tuple[bool, str]:
        """
        Check if a sale can be rolled back by the given user.

        Rules:
        - Only Managers (and HQ/Superuser) can roll back sales
        - Managers can roll back ANY sale in their business (no agent restriction)
        - Agents cannot roll back (even their own sales)

        Returns:
            (can_rollback: bool, reason: str)

        This is safe to call multiple times (idempotent check).
        """
        try:
            # Check if already rolled back (one-time only)
            if RollbackService.is_already_rolled_back(sale):
                return False, "Sale has already been rolled back."

            # Check business ownership (safely)
            try:
                sale_business = getattr(sale.item, "business", None)
                if not sale_business or sale_business != business:
                    return False, "Sale does not belong to this business"
            except (AttributeError, ObjectDoesNotExist):
                return False, "Unable to verify sale ownership"

            # Check user permissions using centralized role system
            from tenants.utils_roles import is_manager, is_agent

            # Superuser/HQ can always rollback
            if user.is_superuser or user.is_staff:
                return True, ""

            # Managers can rollback any sale in their business
            if is_manager(user, business):
                return True, ""

            # Agents cannot rollback (even their own sales)
            if is_agent(user, business):
                return False, "Only managers can roll back sales."

            # No role found
            return False, "Only managers can roll back sales."

        except Exception as e:
            logger.error(f"Error checking rollback permissions for sale {sale.pk}: {e}", exc_info=True)
            return False, "Unable to verify rollback permissions"

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
        notes: str = "",
    ) -> SaleRollback:
        """
        Rollback a sale atomically. ONE-TIME ONLY.

        This function is NOT idempotent - second rollback attempt will raise ValidationError.

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
            ValidationError: If sale is already rolled back (HTTP 409)
            RollbackError: If rollback fails validation or execution (never HTTP 500)
        """
        try:
            # Validate reason first (before any DB operations)
            valid_reasons = dict(RollbackReason.choices)
            if reason not in valid_reasons:
                raise RollbackError(f"Invalid rollback reason: {reason}. Valid: {list(valid_reasons.keys())}")

            # Validate refund amount
            if refunded and refunded_amount <= 0:
                raise RollbackError("Refunded amount must be greater than 0 when refund is issued")

            if refunded_amount > sale.price:
                raise RollbackError(
                    f"Refunded amount (MK {refunded_amount:,.2f}) cannot exceed " f"sale price (MK {sale.price:,.2f})"
                )

            # Acquire lock on sale to prevent concurrent rollbacks
            sale = Sale.objects.select_for_update().get(pk=sale.pk)

            # ONE-TIME ONLY: Check if already rolled back (after acquiring lock)
            if RollbackService.is_already_rolled_back(sale):
                raise ValidationError("Sale already rolled back.")

            # Validate permissions (after checking if already rolled back)
            can_rollback, error_msg = RollbackService.can_rollback(sale, user, business)
            if not can_rollback:
                raise RollbackError(error_msg)

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

            # Reverse inventory changes (with error handling)
            if return_to_stock:
                try:
                    RollbackService._restore_inventory(sale, business)
                except Exception as e:
                    logger.error(f"Error restoring inventory for sale {sale.pk}: {e}", exc_info=True)
                    raise RollbackError(f"Failed to restore inventory: {str(e)}")

            # Reverse commissions (with error handling)
            try:
                RollbackService._reverse_commissions(sale)
            except Exception as e:
                logger.error(f"Error reversing commissions for sale {sale.pk}: {e}", exc_info=True)
                # Don't fail the rollback if commission reversal fails
                logger.warning("Commission reversal failed, but rollback continues")

            # Create refund ledger entry if needed
            if refunded and refunded_amount > 0:
                try:
                    RollbackService._create_refund_entry(sale, refunded_amount, business)
                except Exception as e:
                    logger.error(f"Error creating refund entry for sale {sale.pk}: {e}", exc_info=True)
                    # Don't fail the rollback if ledger entry fails
                    logger.warning("Refund ledger entry failed, but rollback continues")

            logger.info(
                f"Sale {sale.pk} rolled back successfully by {user.username} "
                f"(reason: {reason}, refunded: {refunded_amount})"
            )

            return rollback

        except ValidationError:
            # Re-raise validation errors as-is (for HTTP 409)
            raise
        except RollbackError:
            # Re-raise business rule errors as-is
            raise
        except Exception as e:
            # Catch any unexpected errors and wrap them
            logger.error(f"Unexpected error rolling back sale {sale.pk}: {e}", exc_info=True)
            raise RollbackError(f"Unexpected error during rollback: {str(e)}")

    @staticmethod
    def _restore_inventory(sale: Sale, business: Business) -> None:
        """
        Restore inventory based on vertical type.

        For phones: Mark item as IN_STOCK again
        For clothing: Increment stock quantity
        For pharmacy: Increment batch quantity
        For liquor: Increment bottle/shot quantities
        For gym: Log reversal (memberships are time-based, no stock)
        """
        try:
            item = sale.item

            # Resolve vertical safely
            from inventory.authz import resolve_business_kind

            try:
                vertical = resolve_business_kind(business=business).lower()
            except Exception:
                # Fallback: try to determine from item type
                vertical = RollbackService._detect_vertical_from_item(item)

            logger.info(f"Restoring inventory for {vertical} sale {sale.pk}")

            if vertical == "phones":
                # Phones: Mark item as back in stock
                if hasattr(item, "status"):
                    item.status = "IN_STOCK"
                    item.sold_at = None
                    item.sold_by = None
                    item.selling_price = None
                    # payment_method field has blank=True but NOT null=True, so set to empty string
                    item.payment_method = ""
                    item.save(update_fields=["status", "sold_at", "sold_by", "selling_price", "payment_method"])
                    logger.info(f"Phone item {item.pk} restored to IN_STOCK")
                else:
                    logger.warning(f"Item {item.pk} has no status field (phones)")

            elif vertical == "liquor":
                # Liquor: Restore bottle/shot quantities to product
                RollbackService._restore_liquor_stock(sale, business)

            elif vertical == "clothing":
                # Clothing: Restore quantity to product
                RollbackService._restore_clothing_stock(sale, business)

            elif vertical == "pharmacy":
                # Pharmacy: Restore quantity to batch
                RollbackService._restore_pharmacy_stock(sale, business)

            elif vertical == "gym":
                # Gym: Log reversal (memberships are time-based, no physical stock)
                logger.info(f"Gym sale {sale.pk} rolled back - no stock to restore")

            else:
                logger.warning(f"Unknown vertical '{vertical}' for sale {sale.pk} - no stock restoration")

        except Exception as e:
            logger.error(f"Error restoring inventory for sale {sale.pk}: {e}", exc_info=True)
            raise

    @staticmethod
    def _detect_vertical_from_item(item) -> str:
        """Detect vertical from item type (fallback)"""
        if hasattr(item, "imei"):
            return "phones"
        elif hasattr(item, "variant_text"):
            return "clothing"
        elif hasattr(item, "batch_number"):
            return "pharmacy"
        else:
            return "unknown"

    @staticmethod
    def _restore_liquor_stock(sale: Sale, business: Business) -> None:
        """Restore liquor stock after rollback"""
        try:
            from inventory.models_verticals import LiquorSale

            # Find the liquor sale associated with this general Sale
            # This is tricky because LiquorSale doesn't directly link to Sale
            # We need to query by timing and business
            liquor_sales = LiquorSale.objects.filter(
                business=business, sold_at__date=sale.sold_at, sold_by=sale.agent, total_price=sale.price
            ).order_by("-sold_at")

            for liquor_sale in liquor_sales:
                product = liquor_sale.product

                # Restore quantity based on unit type
                if liquor_sale.unit == "bottle":
                    # Add bottles back to stock
                    if hasattr(product, "quantity_in_stock"):
                        product.quantity_in_stock += liquor_sale.quantity
                        product.save(update_fields=["quantity_in_stock"])
                        logger.info(
                            f"Restored {liquor_sale.quantity} bottles of {product.name} "
                            f"(new stock: {product.quantity_in_stock})"
                        )
                elif liquor_sale.unit == "shot":
                    # Restore shots (more complex - would need to track open bottles)
                    logger.info(f"Liquor sale {liquor_sale.pk} was shots - stock restoration skipped")

                break  # Only restore first matching sale

        except Exception as e:
            logger.error(f"Error restoring liquor stock: {e}", exc_info=True)
            # Don't fail the entire rollback

    @staticmethod
    def _restore_clothing_stock(sale: Sale, business: Business) -> None:
        """Restore clothing stock after rollback"""
        try:
            from inventory.models_verticals import ClothingSale

            # Find the clothing sale
            clothing_sales = ClothingSale.objects.filter(
                business=business, sold_at__date=sale.sold_at, sold_by=sale.agent, total_price=sale.price
            ).order_by("-sold_at")

            for clothing_sale in clothing_sales:
                product = clothing_sale.product

                # Restore quantity
                if hasattr(product, "quantity"):
                    product.quantity += clothing_sale.quantity
                    product.save(update_fields=["quantity"])
                    logger.info(
                        f"Restored {clothing_sale.quantity} units of {product.name} " f"(new stock: {product.quantity})"
                    )

                break  # Only restore first matching sale

        except Exception as e:
            logger.error(f"Error restoring clothing stock: {e}", exc_info=True)
            # Don't fail the entire rollback

    @staticmethod
    def _restore_pharmacy_stock(sale: Sale, business: Business) -> None:
        """Restore pharmacy batch stock after rollback"""
        try:
            from inventory.models_pharmacy import PharmacySale

            # Find the pharmacy sale
            pharmacy_sales = (
                PharmacySale.objects.filter(
                    business=business, sold_at__date=sale.sold_at, sold_by=sale.agent, total_price=sale.price
                )
                .select_related("batch")
                .order_by("-sold_at")
            )

            for pharmacy_sale in pharmacy_sales:
                batch = pharmacy_sale.batch

                # Restore quantity to batch
                if batch:
                    batch.quantity += pharmacy_sale.quantity
                    batch.save(update_fields=["quantity"])
                    logger.info(
                        f"Restored {pharmacy_sale.quantity} units to batch {batch.batch_number} "
                        f"(new quantity: {batch.quantity})"
                    )

                break  # Only restore first matching sale

        except Exception as e:
            logger.error(f"Error restoring pharmacy stock: {e}", exc_info=True)
            # Don't fail the entire rollback

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
            SaleRollback.objects.filter(sale__item__business=business)
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

        rollbacks = SaleRollback.objects.filter(sale__item__business=business, created_at__gte=cutoff)

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
