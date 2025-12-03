# backups/helpers.py
"""
Helpers for exporting business data to CSV files and ZIP archives.
"""
from __future__ import annotations

import csv
import os
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from django.apps import apps
from django.core.files.base import File
from django.db.models import QuerySet, Model
from django.utils import timezone

from tenants.models import Business


def export_queryset_to_csv(queryset: QuerySet, csv_path: Path, fields: List[str] = None) -> int:
    """
    Export a queryset to CSV file.
    
    Args:
        queryset: Django queryset to export
        csv_path: Path to write CSV file
        fields: List of field names to include (if None, includes all)
    
    Returns:
        Number of rows exported
    """
    if not queryset.exists():
        # Create empty CSV with headers
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if fields:
                writer.writerow(fields)
        return 0
    
    # Get model fields
    model = queryset.model
    if not fields:
        fields = [f.name for f in model._meta.get_fields() if not f.many_to_many and not f.one_to_many]
    
    count = 0
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        
        for obj in queryset.iterator(chunk_size=500):
            row = {}
            for field in fields:
                try:
                    value = getattr(obj, field)
                    # Convert common types to string
                    if hasattr(value, 'isoformat'):  # datetime/date
                        row[field] = value.isoformat()
                    elif hasattr(value, 'pk'):  # ForeignKey
                        row[field] = value.pk
                    elif value is None:
                        row[field] = ''
                    else:
                        row[field] = str(value)
                except (AttributeError, ValueError):
                    row[field] = ''
            
            writer.writerow(row)
            count += 1
    
    return count


def export_business_data_to_zip(business: Business) -> tuple[Path, Dict[str, int]]:
    """
    Export all data for a business to a ZIP file.
    
    Args:
        business: Business instance to export
    
    Returns:
        Tuple of (zip_file_path, records_count_dict)
    
    Raises:
        Exception: If export fails
    """
    # Create temp directory for CSV files
    temp_dir = Path(tempfile.mkdtemp(prefix='backup_'))
    records_count = {}
    
    try:
        # ============================================================
        # CORE BUSINESS DATA
        # ============================================================
        
        # Business info
        from tenants.models import Business, Membership
        business_data = Business.objects.filter(pk=business.pk)
        count = export_queryset_to_csv(
            business_data,
            temp_dir / 'business.csv',
            ['id', 'name', 'business_kind', 'created_at']
        )
        records_count['business'] = count
        
        # Memberships (users in this business)
        memberships = Membership.objects.filter(business=business)
        count = export_queryset_to_csv(
            memberships,
            temp_dir / 'memberships.csv',
            ['id', 'user_id', 'business_id', 'role', 'status', 'joined_at']
        )
        records_count['memberships'] = count
        
        # Locations
        from inventory.models import Location
        locations = Location.objects.filter(business=business)
        count = export_queryset_to_csv(
            locations,
            temp_dir / 'locations.csv',
            ['id', 'name', 'city', 'latitude', 'longitude', 'is_default']
        )
        records_count['locations'] = count
        
        # ============================================================
        # INVENTORY DATA
        # ============================================================
        
        # Phone inventory items
        from inventory.models import InventoryItem
        inventory = InventoryItem.objects.filter(business=business)
        count = export_queryset_to_csv(
            inventory,
            temp_dir / 'inventory_items.csv',
            ['id', 'imei', 'brand', 'model', 'cost', 'sell_price', 'status', 
             'scanned_at', 'sold_at', 'location_id', 'payment_method']
        )
        records_count['inventory_items'] = count
        
        # MerchProduct (non-phone products)
        from inventory.models import MerchProduct
        products = MerchProduct.objects.filter(business=business)
        count = export_queryset_to_csv(
            products,
            temp_dir / 'merch_products.csv',
            ['id', 'sku', 'name', 'category', 'cost', 'sell_price', 'created_at']
        )
        records_count['merch_products'] = count
        
        # ============================================================
        # SALES DATA
        # ============================================================
        
        # Phone sales
        from sales.models import Sale
        sales = Sale.objects.filter(location__business=business)
        count = export_queryset_to_csv(
            sales,
            temp_dir / 'sales.csv',
            ['id', 'item_id', 'agent_id', 'location_id', 'sold_at', 'price', 
             'commission_pct', 'payment_method', 'created_at']
        )
        records_count['sales'] = count
        
        # ============================================================
        # WALLET DATA
        # ============================================================
        
        from wallet.models import WalletTransaction
        # Get all transactions for users who are members of this business
        member_user_ids = memberships.values_list('user_id', flat=True)
        wallet_txns = WalletTransaction.objects.filter(agent_id__in=member_user_ids)
        count = export_queryset_to_csv(
            wallet_txns,
            temp_dir / 'wallet_transactions.csv',
            ['id', 'ledger', 'agent_id', 'type', 'amount', 'note', 'reference',
             'effective_date', 'created_at', 'created_by_id']
        )
        records_count['wallet_transactions'] = count
        
        # ============================================================
        # TIMELOGS DATA
        # ============================================================
        
        from timelogs.models import AgentWorkLog, LocationPing
        work_logs = AgentWorkLog.objects.filter(business=business)
        count = export_queryset_to_csv(
            work_logs,
            temp_dir / 'work_logs.csv',
            ['id', 'agent_id', 'business_id', 'location_id', 'work_date',
             'first_seen_at', 'last_seen_at', 'total_on_site_minutes',
             'total_idle_minutes', 'penalty_amount', 'bonus_amount']
        )
        records_count['work_logs'] = count
        
        # Location pings (optional - can be large)
        pings = LocationPing.objects.filter(work_log__business=business)
        count = export_queryset_to_csv(
            pings,
            temp_dir / 'location_pings.csv',
            ['id', 'work_log_id', 'timestamp', 'latitude', 'longitude', 'is_inside_geofence']
        )
        records_count['location_pings'] = count
        
        # ============================================================
        # LAYBY DATA
        # ============================================================
        
        try:
            from layby.models import LaybyOrder, LaybyPayment
            # Layby orders created by members of this business
            layby_orders = LaybyOrder.objects.filter(created_by_id__in=member_user_ids)
            count = export_queryset_to_csv(
                layby_orders,
                temp_dir / 'layby_orders.csv',
                ['id', 'ref', 'customer_name', 'customer_phone', 'id_number',
                 'item_name', 'sku', 'total_price', 'deposit_amount', 'status',
                 'created_at', 'created_by_id']
            )
            records_count['layby_orders'] = count
            
            # Layby payments
            layby_payments = LaybyPayment.objects.filter(order__in=layby_orders)
            count = export_queryset_to_csv(
                layby_payments,
                temp_dir / 'layby_payments.csv',
                ['id', 'order_id', 'amount', 'method', 'tx_ref', 'received_at', 'received_by_id']
            )
            records_count['layby_payments'] = count
        except Exception:
            # Layby might not be installed
            pass
        
        # ============================================================
        # VERTICAL-SPECIFIC DATA
        # ============================================================
        
        # LIQUOR
        try:
            from inventory.models_verticals import (
                LiquorShift, LiquorShiftStock, LiquorSale, LiquorCredit, LiquorCreditPayment
            )
            
            liquor_shifts = LiquorShift.objects.filter(business=business)
            count = export_queryset_to_csv(
                liquor_shifts,
                temp_dir / 'liquor_shifts.csv',
                ['id', 'business_id', 'location_id', 'barman_id', 'started_at',
                 'ended_at', 'status', 'total_sales_amount', 'total_profit_amount']
            )
            records_count['liquor_shifts'] = count
            
            stock = LiquorShiftStock.objects.filter(shift__business=business)
            count = export_queryset_to_csv(
                stock,
                temp_dir / 'liquor_shift_stock.csv',
                ['id', 'shift_id', 'product_id', 'opening_bottles', 'closing_bottles',
                 'bottles_sold', 'bottles_count', 'variance']
            )
            records_count['liquor_shift_stock'] = count
            
            sales = LiquorSale.objects.filter(shift__business=business)
            count = export_queryset_to_csv(
                sales,
                temp_dir / 'liquor_sales.csv',
                ['id', 'shift_id', 'product_id', 'unit_type', 'quantity', 'price_per_unit',
                 'total_amount', 'sale_type', 'sold_at']
            )
            records_count['liquor_sales'] = count
            
            credits = LiquorCredit.objects.filter(sale__shift__business=business)
            count = export_queryset_to_csv(
                credits,
                temp_dir / 'liquor_credits.csv',
                ['id', 'sale_id', 'customer_name', 'customer_phone', 'amount',
                 'amount_paid', 'status', 'created_at']
            )
            records_count['liquor_credits'] = count
            
            credit_payments = LiquorCreditPayment.objects.filter(credit__sale__shift__business=business)
            count = export_queryset_to_csv(
                credit_payments,
                temp_dir / 'liquor_credit_payments.csv',
                ['id', 'credit_id', 'amount', 'payment_method', 'transaction_id',
                 'submitted_at', 'submitted_by_id', 'status']
            )
            records_count['liquor_credit_payments'] = count
        except Exception:
            # Liquor models might not be available
            pass
        
        # GYM
        try:
            from inventory.models_verticals import GymMember, GymMemberPayment
            
            gym_members = GymMember.objects.filter(business=business)
            count = export_queryset_to_csv(
                gym_members,
                temp_dir / 'gym_members.csv',
                ['id', 'business_id', 'name', 'phone', 'id_number', 'membership_type',
                 'monthly_fee', 'status', 'joined_at', 'last_payment_date']
            )
            records_count['gym_members'] = count
            
            payments = GymMemberPayment.objects.filter(member__business=business)
            count = export_queryset_to_csv(
                payments,
                temp_dir / 'gym_payments.csv',
                ['id', 'member_id', 'amount', 'payment_method', 'period_start',
                 'period_end', 'paid_at', 'received_by_id']
            )
            records_count['gym_payments'] = count
        except Exception:
            pass
        
        # CLOTHING
        try:
            from inventory.models_verticals import ClothingSale
            
            clothing_sales = ClothingSale.objects.filter(business=business)
            count = export_queryset_to_csv(
                clothing_sales,
                temp_dir / 'clothing_sales.csv',
                ['id', 'business_id', 'product_id', 'quantity', 'unit_price',
                 'total_amount', 'payment_method', 'sold_at', 'sold_by_id']
            )
            records_count['clothing_sales'] = count
        except Exception:
            pass
        
        # PHARMACY
        try:
            from inventory.models_pharmacy import PharmacyBatch, PharmacySale
            
            batches = PharmacyBatch.objects.filter(business=business)
            count = export_queryset_to_csv(
                batches,
                temp_dir / 'pharmacy_batches.csv',
                ['id', 'business_id', 'product_id', 'batch_number', 'quantity',
                 'expiry_date', 'received_at']
            )
            records_count['pharmacy_batches'] = count
            
            pharmacy_sales = PharmacySale.objects.filter(business=business)
            count = export_queryset_to_csv(
                pharmacy_sales,
                temp_dir / 'pharmacy_sales.csv',
                ['id', 'business_id', 'product_id', 'batch_id', 'quantity',
                 'unit_price', 'total_amount', 'sold_at', 'sold_by_id']
            )
            records_count['pharmacy_sales'] = count
        except Exception:
            pass
        
        # ============================================================
        # CREATE ZIP FILE
        # ============================================================
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"backup_{business.name}_{timestamp}.zip".replace(' ', '_')
        zip_path = temp_dir / zip_filename
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all CSV files
            for csv_file in temp_dir.glob('*.csv'):
                zipf.write(csv_file, csv_file.name)
            
            # Add metadata file
            metadata_path = temp_dir / 'backup_metadata.txt'
            with open(metadata_path, 'w') as f:
                f.write(f"CircuitCity Data Backup\n")
                f.write(f"========================\n\n")
                f.write(f"Business: {business.name}\n")
                f.write(f"Business ID: {business.pk}\n")
                f.write(f"Business Type: {business.business_kind}\n")
                f.write(f"Generated: {timezone.now().isoformat()}\n\n")
                f.write(f"Records Count:\n")
                for model, count in sorted(records_count.items()):
                    f.write(f"  {model}: {count:,}\n")
            
            zipf.write(metadata_path, 'backup_metadata.txt')
        
        return zip_path, records_count
    
    except Exception as e:
        # Clean up temp directory on error
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise e


def cleanup_temp_files(zip_path: Path) -> None:
    """Clean up temporary files after backup."""
    import shutil
    if zip_path and zip_path.parent.name.startswith('backup_'):
        shutil.rmtree(zip_path.parent, ignore_errors=True)

