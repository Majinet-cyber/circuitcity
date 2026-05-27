# sales/services/phone_sale_edit.py
"""
Phone Sale Edit Service
========================
Service for editing phone sale details (price and IMEI) without rolling back.

This allows correcting sale information without undoing the sale or affecting stock.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from sales.models import Sale, SaleCommission
from inventory.models import InventoryItem
from tenants.models import Business

User = get_user_model()
logger = logging.getLogger(__name__)


class SaleEditError(Exception):
    """Raised when a sale edit operation fails validation or business rules"""

    pass


class PhoneSaleEditService:
    """
    Service for editing phone sale details safely and atomically.
    """

    @staticmethod
    @transaction.atomic
    def edit_phone_sale(
        *,
        sale_id: int,
        business: Business,
        user: User,
        new_selling_price: Decimal,
        new_imei: Optional[str] = None,
    ) -> Sale:
        """
        Edit a phone sale's price and/or IMEI without rolling back.

        This function:
        - Updates Sale.price
        - Updates InventoryItem.selling_price
        - Updates InventoryItem.imei (if provided)
        - Recalculates and updates SaleCommission (if exists)
        - Updates WalletTransaction commission amount (if exists)
        - Does NOT affect stock quantities
        - Does NOT mark sale as rolled back

        Args:
            sale_id: ID of the sale to edit
            business: Business context (for tenant safety)
            user: User performing the edit
            new_selling_price: New selling price (must be >= 0)
            new_imei: New IMEI (optional, but required if product is IMEI-tracked)

        Returns:
            Updated Sale instance

        Raises:
            SaleEditError: If edit fails validation or execution
        """
        try:
            # Acquire lock on sale to prevent concurrent edits
            sale = (
                Sale.objects.select_for_update()
                .select_related("item", "item__product", "agent", "location")
                .get(pk=sale_id)
            )

            # Validate business ownership
            sale_business = getattr(sale.item, "business", None)
            if not sale_business or sale_business != business:
                raise SaleEditError("Sale does not belong to this business")

            # Validate sale is not rolled back
            if sale.is_rolled_back:
                raise SaleEditError("Cannot edit a sale that has been rolled back")

            # Validate new price
            if new_selling_price < 0:
                raise SaleEditError("Selling price must be >= 0")

            # Validate IMEI if provided
            imei_digits = None
            if new_imei is not None:
                new_imei = new_imei.strip()
                if new_imei:
                    # Basic IMEI validation (15 digits)
                    imei_digits = "".join(ch for ch in new_imei if ch.isdigit())
                    if len(imei_digits) != 15:
                        raise SaleEditError(f"IMEI must be exactly 15 digits. Got {len(imei_digits)} digits.")

                    # Check for IMEI conflicts (if another active sale/stock has this IMEI)
                    conflicting_item = (
                        InventoryItem.objects.filter(business=business, imei=imei_digits, status="SOLD")
                        .exclude(pk=sale.item_id)
                        .first()
                    )

                    if conflicting_item:
                        raise SaleEditError(
                            f"IMEI {imei_digits} is already assigned to another sold item "
                            f"(Item #{conflicting_item.pk})"
                        )

                    # Check for conflicts with in-stock items (optional - you may want to allow this)
                    in_stock_conflict = (
                        InventoryItem.objects.filter(business=business, imei=imei_digits, status="IN_STOCK")
                        .exclude(pk=sale.item_id)
                        .first()
                    )

                    if in_stock_conflict:
                        logger.warning(
                            f"IMEI {imei_digits} exists in stock (Item #{in_stock_conflict.pk}), "
                            f"but allowing edit to proceed"
                        )

            # Get the item
            item = sale.item

            # Store old values for logging
            old_price = sale.price
            old_imei = getattr(item, "imei", None)

            # Update Sale.price
            sale.price = new_selling_price
            sale.save(update_fields=["price"])

            # Update InventoryItem.selling_price
            if hasattr(item, "selling_price"):
                item.selling_price = new_selling_price
                item.save(update_fields=["selling_price"])

            # Update InventoryItem.imei if provided
            if imei_digits is not None:
                if hasattr(item, "imei"):
                    item.imei = imei_digits
                    item.save(update_fields=["imei"])

            # Recalculate and update SaleCommission if it exists
            PhoneSaleEditService._update_commission(sale, business)

            # Update WalletTransaction commission if it exists
            PhoneSaleEditService._update_wallet_commission(sale, business, old_price)

            logger.info(
                f"Sale #{sale.pk} edited by {user.username}: "
                f"price {old_price} -> {new_selling_price}, "
                f"IMEI {old_imei} -> {imei_digits if imei_digits else 'unchanged'}"
            )

            return sale

        except Sale.DoesNotExist:
            raise SaleEditError(f"Sale #{sale_id} not found")
        except SaleEditError:
            # Re-raise business rule errors as-is
            raise
        except Exception as e:
            logger.error(f"Unexpected error editing sale {sale_id}: {e}", exc_info=True)
            raise SaleEditError(f"Unexpected error during sale edit: {str(e)}")

    @staticmethod
    def _update_commission(sale: Sale, business: Business) -> None:
        """
        Recalculate and update SaleCommission if it exists.
        """
        try:
            commission = SaleCommission.objects.filter(sale=sale).first()
            if not commission:
                return  # No commission record to update

            # Get commission config
            from sales.models import CommissionConfig

            config = CommissionConfig.get_active(business)

            # Recalculate base commission
            if config:
                if config.commission_mode == "FIXED":
                    new_base = config.fixed_commission_amount
                else:
                    new_base = sale.price * (config.base_commission_pct / Decimal("100.00"))
            else:
                # Fallback: use sale's commission_pct
                new_base = sale.commission_amount

            # Update base commission (bonuses/penalties remain unchanged)
            commission.base_commission = new_base
            commission.compute_net()  # Recalculate net_amount
            commission.save(update_fields=["base_commission", "net_amount"])

            logger.info(f"Updated commission for Sale #{sale.pk}: base={new_base}, net={commission.net_amount}")

        except Exception as e:
            logger.error(f"Error updating commission for sale {sale.pk}: {e}", exc_info=True)
            # Don't fail the edit if commission update fails
            logger.warning("Commission update failed, but sale edit continues")

    @staticmethod
    def _update_wallet_commission(sale: Sale, business: Business, old_price: Decimal) -> None:
        """
        Update WalletTransaction commission amount if it exists.
        """
        try:
            from wallet.models import WalletTransaction, TxnType, Ledger

            # Find the commission transaction for this sale
            commission_txn = WalletTransaction.objects.filter(
                business=business,
                agent=sale.agent,
                type=TxnType.COMMISSION,
                meta__sale_id=sale.id,
            ).first()

            if not commission_txn:
                return  # No wallet transaction to update

            # Recalculate commission amount
            from sales.models import CommissionConfig

            config = CommissionConfig.get_active(business)

            if config:
                if config.commission_mode == "FIXED":
                    new_amount = config.fixed_commission_amount
                else:
                    new_amount = sale.price * (config.base_commission_pct / Decimal("100.00"))
            else:
                # Fallback calculation
                new_amount = sale.commission_amount

            # Update the transaction amount
            old_amount = commission_txn.amount
            commission_txn.amount = new_amount

            # Update metadata
            if commission_txn.meta:
                commission_txn.meta["sale_price"] = str(sale.price)
            else:
                commission_txn.meta = {"sale_price": str(sale.price)}

            commission_txn.note = f"Commission for Sale #{sale.id} (edited)"
            commission_txn.save(update_fields=["amount", "meta", "note"])

            logger.info(f"Updated wallet commission for Sale #{sale.pk}: " f"{old_amount} -> {new_amount}")

        except ImportError:
            # Wallet app not available, skip
            pass
        except Exception as e:
            logger.error(f"Error updating wallet commission for sale {sale.pk}: {e}", exc_info=True)
            # Don't fail the edit if wallet update fails
            logger.warning("Wallet commission update failed, but sale edit continues")

    @staticmethod
    def can_edit_sale(sale: Sale, user: User, business: Business) -> tuple[bool, str]:
        """
        Check if a sale can be edited by the given user.

        Returns:
            (can_edit: bool, reason: str)
        """
        try:
            # Check if sale is rolled back
            if sale.is_rolled_back:
                return False, "Cannot edit a sale that has been rolled back"

            # Check business ownership
            sale_business = getattr(sale.item, "business", None)
            if not sale_business or sale_business != business:
                return False, "Sale does not belong to this business"

            # Check user permissions (same as rollback permissions)
            from tenants.models import Membership
            from django.db.models import Case, When, Value, IntegerField

            membership = (
                Membership.objects.filter(user=user, business=business, status="ACTIVE")
                .annotate(
                    role_priority=Case(
                        When(role="MANAGER", then=Value(1)),
                        When(role="OWNER", then=Value(1)),
                        When(role="ADMIN", then=Value(1)),
                        When(role="AGENT", then=Value(2)),
                        default=Value(3),
                        output_field=IntegerField(),
                    )
                )
                .order_by("role_priority")
                .first()
            )

            if not membership:
                return False, "User is not an active member of this business"

            role = membership.role.upper()

            # Managers, Owners, and Admins can edit any sale
            if role in ["MANAGER", "OWNER", "ADMIN", "HQ_ADMIN"]:
                return True, ""

            # Agents can only edit their own sales (same as rollback)
            if role == "AGENT":
                if not sale.agent or sale.agent.id != user.id:
                    return False, "Agents can only edit their own sales"
                return True, ""

            return False, "Insufficient permissions to edit sales"

        except Exception as e:
            logger.error(f"Error checking edit permissions for sale {sale.pk}: {e}", exc_info=True)
            return False, "Unable to verify edit permissions"


__all__ = ["PhoneSaleEditService", "SaleEditError"]
