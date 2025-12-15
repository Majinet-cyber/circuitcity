# inventory/analytics/adapters/base.py
"""
Base adapter protocol for vertical-specific analytics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet


class AnalyticsAdapter(ABC):
    """
    Base adapter interface for vertical-specific analytics.
    Each vertical must implement this interface.
    """
    
    @abstractmethod
    def get_sales_queryset(self, business, location=None) -> QuerySet:
        """Get base sales queryset for this vertical."""
        pass
    
    @abstractmethod
    def get_stock_queryset(self, business, location=None) -> QuerySet:
        """Get base stock queryset for this vertical."""
        pass
    
    @abstractmethod
    def get_costs_queryset(self, business, location=None) -> QuerySet:
        """Get costs queryset (WalletTransaction with ledger=COMPANY)."""
        pass
    
    @abstractmethod
    def kpis(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate KPIs for the period.
        
        Returns:
            Dict with keys: revenue, profit, total_sales, avg_order_value, gross_margin, costs
        """
        pass
    
    @abstractmethod
    def charts(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
        payment_method: Optional[str] = None,
        search_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate chart data.
        
        Returns:
            Dict with keys: sales_trend, profit_trend, payment_mix, top_products, top_agents, stock_overview
        """
        pass
    
    def vertical_sections(
        self,
        business,
        start_date: date,
        end_date: date,
        location=None,
    ) -> Dict[str, Any]:
        """
        Vertical-specific sections (e.g., gym: new members, pharmacy: expiring stock).
        Override in subclasses for vertical-specific data.
        
        Returns:
            Dict with vertical-specific metrics (empty dict if none)
        """
        return {}
    
    def get_search_fields(self) -> List[str]:
        """Return list of field names to search for this vertical."""
        return []

