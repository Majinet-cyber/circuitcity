# inventory/analytics/adapters/phones.py
"""
Analytics adapter for phones vertical.
Phones use InventoryItem with status="SOLD" for sales tracking.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet, Sum, Count, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from inventory.models import InventoryItem
from inventory.analytics.adapters.base import AnalyticsAdapter
from inventory.analytics.common import (
    apply_business_scope, apply_location_filter, apply_payment_method_filter,
    apply_search_filter
)
from wallet.models import WalletTransaction, Ledger, TxnType


class PhonesAdapter(AnalyticsAdapter):
    """Analytics adapter for phones vertical."""
    
    def get_sales_queryset(self, business, location=None) -> QuerySet:
        """Get base sales queryset (InventoryItem with status=SOLD)."""
        qs = InventoryItem.objects.filter(
            business=business,
            status="SOLD",
            sold_at__isnull=False
        ).select_related('product', 'assigned_agent', 'current_location')
        
        if location:
            qs = qs.filter(current_location=location)
        
        return qs
    
    def get_stock_queryset(self, business, location=None) -> QuerySet:
        """Get base stock queryset (InventoryItem with status=IN_STOCK)."""
        qs = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK",
            is_active=True
        ).select_related('product', 'current_location')
        
        if location:
            qs = qs.filter(current_location=location)
        
        return qs
    
    def get_costs_queryset(self, business, location=None) -> QuerySet:
        """Get costs queryset (WalletTransaction with ledger=COMPANY)."""
        qs = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type__in=[TxnType.COST_ONCE_OFF, TxnType.COST_RECURRING]
        )
        # Note: WalletTransaction doesn't have location, so location filter is ignored
        return qs
    
    def get_search_fields(self) -> List[str]:
        """Return search fields for phones."""
        return ['imei', 'product__brand', 'product__model', 'product__variant', 'assigned_agent__username']
    
    def kpis(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calculate KPIs for phones."""
        # Get sales queryset
        sales_qs = self.get_sales_queryset(business, location)
        
        # Apply date filter
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time()))
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)
        
        # Apply filters
        sales_qs = apply_payment_method_filter(sales_qs, payment_method)
        if search_query:
            sales_qs = apply_search_filter(sales_qs, search_query, self.get_search_fields())
        
        # Calculate KPIs
        revenue = sales_qs.aggregate(
            total=Coalesce(Sum('selling_price'), Decimal('0.00'))
        )['total'] or Decimal('0.00')
        
        cost_of_goods = sales_qs.aggregate(
            total=Coalesce(Sum('order_price'), Decimal('0.00'))
        )['total'] or Decimal('0.00')
        
        total_sales = sales_qs.count()
        avg_order_value = revenue / total_sales if total_sales > 0 else Decimal('0.00')
        
        # Get costs
        costs_qs = self.get_costs_queryset(business, location)
        costs_qs = costs_qs.filter(
            Q(type=TxnType.COST_ONCE_OFF, effective_date__gte=start_date, effective_date__lte=end_date) |
            Q(type=TxnType.COST_RECURRING, effective_from__lte=end_date)
        )
        costs = abs(costs_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'))
        
        profit = revenue - cost_of_goods - costs
        gross_margin = ((revenue - cost_of_goods) / revenue * 100) if revenue > 0 else Decimal('0.00')
        
        return {
            'revenue': revenue,
            'profit': profit,
            'total_sales': total_sales,
            'avg_order_value': avg_order_value,
            'gross_margin': gross_margin,
            'costs': costs,
        }
    
    def charts(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate chart data for phones."""
        # Get sales queryset
        sales_qs = self.get_sales_queryset(business, location)
        
        # Apply date filter
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time()))
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)
        
        # Apply filters
        sales_qs = apply_payment_method_filter(sales_qs, payment_method)
        if search_query:
            sales_qs = apply_search_filter(sales_qs, search_query, self.get_search_fields())
        
        # Sales trend (daily)
        daily_sales = sales_qs.annotate(
            day=TruncDate('sold_at')
        ).values('day').annotate(
            revenue=Coalesce(Sum('selling_price'), Decimal('0.00')),
            cost=Coalesce(Sum('order_price'), Decimal('0.00')),
            count=Count('id')
        ).order_by('day')
        
        sales_trend = [
            {
                'date': str(item['day']),
                'date_short': item['day'].strftime('%m/%d') if item['day'] else '',
                'revenue': float(item['revenue']),
                'profit': float(item['revenue'] - item['cost']),
                'count': item['count'],
            }
            for item in daily_sales
        ]
        
        # Profit trend (same as sales trend but with profit)
        profit_trend = sales_trend  # Already includes profit
        
        # Payment mix
        payment_mix = sales_qs.values('payment_method').annotate(
            total=Coalesce(Sum('selling_price'), Decimal('0.00')),
            count=Count('id')
        ).order_by('-total')
        
        total_amount = sum(float(pm['total']) for pm in payment_mix)
        payment_mix_data = []
        for pm in payment_mix:
            amount = float(pm['total'])
            method = pm['payment_method'] or 'CASH'
            payment_mix_data.append({
                'method': method,
                'method_display': method.replace('_', ' ').title(),
                'amount': amount,
                'percentage': (amount / total_amount * 100) if total_amount > 0 else 0,
            })
        
        # Top products (by revenue) - group by brand + model
        from django.db.models import F, Value, CharField
        from django.db.models.functions import Concat, Coalesce as CoalesceFunc
        
        top_products = sales_qs.annotate(
            model_label=CoalesceFunc(
                Concat(
                    F('product__brand'), Value(' '), F('product__model'),
                    output_field=CharField()
                ),
                F('product__model'),
                F('product__name'),
                Value('Unknown'),
                output_field=CharField()
            )
        ).values('model_label').annotate(
            revenue=Coalesce(Sum('selling_price'), Decimal('0.00')),
            units_sold=Count('id')
        ).order_by('-revenue')[:10]
        
        top_products_data = [
            {
                'name': item['model_label'] or 'Unknown',
                'revenue': float(item['revenue']),
                'units_sold': item['units_sold'],
            }
            for item in top_products
        ]
        
        # Top agents
        top_agents = sales_qs.filter(assigned_agent__isnull=False).values(
            'assigned_agent__id', 'assigned_agent__first_name', 'assigned_agent__last_name', 'assigned_agent__username'
        ).annotate(
            revenue=Coalesce(Sum('selling_price'), Decimal('0.00')),
            units_sold=Count('id')
        ).order_by('-revenue')[:10]
        
        top_agents_data = [
            {
                'name': f"{item['assigned_agent__first_name'] or ''} {item['assigned_agent__last_name'] or ''}".strip() or item['assigned_agent__username'] or 'Unknown',
                'revenue': float(item['revenue']),
                'units_sold': item['units_sold'],
            }
            for item in top_agents
        ]
        
        # Stock overview
        stock_qs = self.get_stock_queryset(business, location)
        stock_value = stock_qs.aggregate(
            total=Coalesce(Sum('order_price'), Decimal('0.00'))
        )['total'] or Decimal('0.00')
        
        stock_retail_value = stock_qs.aggregate(
            total=Coalesce(Sum('selling_price'), Decimal('0.00'))
        )['total'] or Decimal('0.00')
        
        # Low stock (items with low quantity - for phones, this might mean items without IMEI or specific conditions)
        # For now, return empty as phones track individual items, not quantities
        low_stock = []
        
        stock_overview = {
            'stock_value': float(stock_value),
            'stock_retail_value': float(stock_retail_value),
            'low_stock_count': len(low_stock),
            'low_stock': low_stock,
        }
        
        return {
            'sales_trend': sales_trend,
            'profit_trend': profit_trend,
            'payment_mix': payment_mix_data,
            'top_products': top_products_data,
            'top_agents': top_agents_data,
            'stock_overview': stock_overview,
        }
    
    def vertical_sections(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
    ) -> Dict[str, Any]:
        """Vertical-specific sections for phones."""
        sales_qs = self.get_sales_queryset(business, location)
        start_dt = timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time()))
        end_dt = timezone.make_aware(timezone.datetime.combine(end_date + timedelta(days=1), timezone.datetime.min.time()))
        sales_qs = sales_qs.filter(sold_at__gte=start_dt, sold_at__lt=end_dt)
        
        # IMEI sales count
        imei_sales = sales_qs.filter(imei__isnull=False).count()
        
        # Top brands
        top_brands = sales_qs.values('product__brand').annotate(
            count=Count('id'),
            revenue=Coalesce(Sum('selling_price'), Decimal('0.00'))
        ).order_by('-revenue')[:5]
        
        return {
            'imei_sales_count': imei_sales,
            'top_brands': [
                {
                    'brand': item['product__brand'] or 'Unknown',
                    'count': item['count'],
                    'revenue': float(item['revenue']),
                }
                for item in top_brands
            ],
        }

