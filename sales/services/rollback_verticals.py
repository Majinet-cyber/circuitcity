# sales/services/rollback_verticals.py
"""
Vertical-Specific Rollback Services
====================================
Rollback handlers for Liquor, Clothing, and Pharmacy verticals.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from tenants.models import Business

User = get_user_model()
logger = logging.getLogger(__name__)


class VerticalRollbackError(Exception):
    """Raised when a vertical-specific rollback fails"""
    pass


class LiquorRollbackService:
    """Rollback service for Liquor vertical"""
    
    @staticmethod
    @transaction.atomic
    def rollback_liquor_sale(
        sale_id: int,
        user: User,
        business: Business,
        reason: str,
        refunded: bool = False,
        refunded_amount: Decimal = Decimal("0.00"),
        return_to_stock: bool = False,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Rollback a liquor sale atomically.
        
        Returns:
            Dict with rollback details
        
        Raises:
            VerticalRollbackError: If rollback fails
        """
        try:
            from inventory.models_verticals import LiquorSale
            
            # Get the liquor sale
            try:
                sale = LiquorSale.objects.select_for_update().get(
                    id=sale_id,
                    business=business
                )
            except LiquorSale.DoesNotExist:
                raise VerticalRollbackError("Liquor sale not found")
            
            # Check if already rolled back (idempotent)
            if hasattr(sale, 'is_rolled_back') and sale.is_rolled_back:
                logger.info(f"Liquor sale {sale_id} already rolled back (idempotent)")
                return {
                    "success": True,
                    "message": "Sale was already rolled back",
                    "sale_id": sale_id,
                }
            
            # Check permissions
            from tenants.models import Membership
            try:
                membership = Membership.objects.get(user=user, business=business)
                role = membership.role.upper()
                
                if role not in ["MANAGER", "OWNER", "ADMIN"]:
                    raise VerticalRollbackError("Only managers can rollback liquor sales")
            except Membership.DoesNotExist:
                raise VerticalRollbackError("User is not a member of this business")
            
            # Validate refund amount
            if refunded and refunded_amount <= 0:
                raise VerticalRollbackError("Refunded amount must be greater than 0")
            
            if refunded_amount > sale.total_price:
                raise VerticalRollbackError(
                    f"Refunded amount (MK {refunded_amount:,.2f}) cannot exceed "
                    f"sale price (MK {sale.total_price:,.2f})"
                )
            
            # Restore stock if requested
            if return_to_stock:
                product = sale.product
                
                if sale.unit == "bottle":
                    # Restore bottles to stock
                    if hasattr(product, 'quantity_in_stock'):
                        product.quantity_in_stock += sale.quantity
                        product.save(update_fields=['quantity_in_stock'])
                        logger.info(
                            f"Restored {sale.quantity} bottles of {product.name} "
                            f"(new stock: {product.quantity_in_stock})"
                        )
                elif sale.unit == "shot":
                    # For shots, we can't easily restore (open bottles)
                    logger.info(f"Liquor sale {sale_id} was shots - stock restoration skipped")
            
            # Mark sale as rolled back (add fields if they don't exist)
            if not hasattr(sale, 'is_rolled_back'):
                # Add rollback tracking fields dynamically
                from django.db import connection
                with connection.cursor() as cursor:
                    table_name = sale._meta.db_table
                    
                    # Check if columns exist
                    cursor.execute(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name='{table_name}' 
                        AND column_name IN ('is_rolled_back', 'rolled_back_at', 'rolled_back_by_id', 'rollback_reason', 'rollback_notes')
                    """)
                    existing_cols = {row[0] for row in cursor.fetchall()}
                    
                    # Add missing columns
                    if 'is_rolled_back' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN is_rolled_back BOOLEAN DEFAULT FALSE")
                    if 'rolled_back_at' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rolled_back_at TIMESTAMP NULL")
                    if 'rolled_back_by_id' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rolled_back_by_id INTEGER NULL")
                    if 'rollback_reason' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rollback_reason VARCHAR(50) NULL")
                    if 'rollback_notes' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rollback_notes TEXT NULL")
            
            # Update sale record
            sale.is_rolled_back = True
            sale.rolled_back_at = timezone.now()
            sale.rolled_back_by = user
            sale.rollback_reason = reason
            sale.rollback_notes = notes
            sale.save()
            
            logger.info(
                f"Liquor sale {sale_id} rolled back successfully by {user.username} "
                f"(reason: {reason}, refunded: {refunded_amount})"
            )
            
            return {
                "success": True,
                "message": "Liquor sale rolled back successfully",
                "sale_id": sale_id,
                "refunded_amount": float(refunded_amount),
                "stock_restored": return_to_stock,
            }
        
        except VerticalRollbackError:
            raise
        except Exception as e:
            logger.error(f"Error rolling back liquor sale {sale_id}: {e}", exc_info=True)
            raise VerticalRollbackError(f"Unexpected error: {str(e)}")


class ClothingRollbackService:
    """Rollback service for Clothing vertical"""
    
    @staticmethod
    @transaction.atomic
    def rollback_clothing_sale(
        sale_id: int,
        user: User,
        business: Business,
        reason: str,
        refunded: bool = False,
        refunded_amount: Decimal = Decimal("0.00"),
        return_to_stock: bool = False,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Rollback a clothing sale atomically.
        
        Returns:
            Dict with rollback details
        
        Raises:
            VerticalRollbackError: If rollback fails
        """
        try:
            from inventory.models_verticals import ClothingSale
            
            # Get the clothing sale
            try:
                sale = ClothingSale.objects.select_for_update().get(
                    id=sale_id,
                    business=business
                )
            except ClothingSale.DoesNotExist:
                raise VerticalRollbackError("Clothing sale not found")
            
            # Check if already rolled back (idempotent)
            if hasattr(sale, 'is_rolled_back') and sale.is_rolled_back:
                logger.info(f"Clothing sale {sale_id} already rolled back (idempotent)")
                return {
                    "success": True,
                    "message": "Sale was already rolled back",
                    "sale_id": sale_id,
                }
            
            # Check permissions
            from tenants.models import Membership
            try:
                membership = Membership.objects.get(user=user, business=business)
                role = membership.role.upper()
                
                if role not in ["MANAGER", "OWNER", "ADMIN"]:
                    raise VerticalRollbackError("Only managers can rollback clothing sales")
            except Membership.DoesNotExist:
                raise VerticalRollbackError("User is not a member of this business")
            
            # Validate refund amount
            if refunded and refunded_amount <= 0:
                raise VerticalRollbackError("Refunded amount must be greater than 0")
            
            if refunded_amount > sale.total_price:
                raise VerticalRollbackError(
                    f"Refunded amount (MK {refunded_amount:,.2f}) cannot exceed "
                    f"sale price (MK {sale.total_price:,.2f})"
                )
            
            # Restore stock if requested
            if return_to_stock:
                product = sale.product
                
                if hasattr(product, 'quantity'):
                    product.quantity += sale.quantity
                    product.save(update_fields=['quantity'])
                    logger.info(
                        f"Restored {sale.quantity} units of {product.name} "
                        f"(new stock: {product.quantity})"
                    )
            
            # Mark sale as rolled back (add fields if they don't exist)
            if not hasattr(sale, 'is_rolled_back'):
                # Add rollback tracking fields dynamically
                from django.db import connection
                with connection.cursor() as cursor:
                    table_name = sale._meta.db_table
                    
                    # Check if columns exist
                    cursor.execute(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name='{table_name}' 
                        AND column_name IN ('is_rolled_back', 'rolled_back_at', 'rolled_back_by_id', 'rollback_reason', 'rollback_notes')
                    """)
                    existing_cols = {row[0] for row in cursor.fetchall()}
                    
                    # Add missing columns
                    if 'is_rolled_back' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN is_rolled_back BOOLEAN DEFAULT FALSE")
                    if 'rolled_back_at' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rolled_back_at TIMESTAMP NULL")
                    if 'rolled_back_by_id' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rolled_back_by_id INTEGER NULL")
                    if 'rollback_reason' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rollback_reason VARCHAR(50) NULL")
                    if 'rollback_notes' not in existing_cols:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN rollback_notes TEXT NULL")
            
            # Update sale record
            sale.is_rolled_back = True
            sale.rolled_back_at = timezone.now()
            sale.rolled_back_by = user
            sale.rollback_reason = reason
            sale.rollback_notes = notes
            sale.save()
            
            logger.info(
                f"Clothing sale {sale_id} rolled back successfully by {user.username} "
                f"(reason: {reason}, refunded: {refunded_amount})"
            )
            
            return {
                "success": True,
                "message": "Clothing sale rolled back successfully",
                "sale_id": sale_id,
                "refunded_amount": float(refunded_amount),
                "stock_restored": return_to_stock,
            }
        
        except VerticalRollbackError:
            raise
        except Exception as e:
            logger.error(f"Error rolling back clothing sale {sale_id}: {e}", exc_info=True)
            raise VerticalRollbackError(f"Unexpected error: {str(e)}")


__all__ = ["LiquorRollbackService", "ClothingRollbackService", "VerticalRollbackError"]

