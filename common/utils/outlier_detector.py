"""
AI-Driven Outlier Detection System
Non-blocking warnings for unusual values

Uses recent business data to detect when entered values are suspiciously high or low.
Never blocks submission - only warns the user.

Statistical approach: Median + IQR (Interquartile Range)
"""

from decimal import Decimal
from typing import Optional, Dict, List, Tuple
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg, StdDev, Max, Min, Count, Q
import statistics


class OutlierDetector:
    """Detects unusual values based on historical business data"""
    
    def __init__(self, business, lookback_days=30):
        """
        Initialize detector with business context.
        
        Args:
            business: Business object
            lookback_days: Number of days to look back for historical data
        """
        self.business = business
        self.lookback_days = lookback_days
        self.start_date = timezone.now() - timedelta(days=lookback_days)
    
    def check_sale_amount(
        self,
        amount: Decimal,
        vertical: Optional[str] = None
    ) -> Dict:
        """
        Check if a sale amount is unusual.
        
        Args:
            amount: The sale amount to check
            vertical: Vertical type (phones, liquor, gym, etc.)
        
        Returns:
            Dict with keys: is_outlier, warning_message, typical_range, confidence
        """
        # Get recent sales for this business
        from inventory.models_unique_products import UniqueSale
        
        recent_sales = UniqueSale.objects.filter(
            business=self.business,
            sold_at__gte=self.start_date,
            is_deleted=False
        )
        
        if vertical:
            recent_sales = recent_sales.filter(product__vertical=vertical)
        
        # Calculate sale amounts
        sale_amounts = []
        for sale in recent_sales:
            sale_amount = sale.quantity * sale.unit_price
            sale_amounts.append(float(sale_amount))
        
        # Need at least 5 sales to make a determination
        if len(sale_amounts) < 5:
            return {
                'is_outlier': False,
                'warning_message': None,
                'typical_range': None,
                'confidence': 'low',
                'reason': 'Insufficient historical data'
            }
        
        # Statistical analysis
        result = self._analyze_outlier(float(amount), sale_amounts)
        
        if result['is_outlier']:
            # Generate friendly warning message
            median = result['median']
            iqr = result['iqr']
            
            if result['direction'] == 'high':
                warning_message = (
                    f"This value looks unusually high compared to your recent sales. "
                    f"Your typical sales range from MWK {result['lower_bound']:,.0f} to MWK {result['upper_bound']:,.0f}. "
                    f"Did you mean MWK {median:,.0f}?"
                )
            else:
                warning_message = (
                    f"This value is lower than usual for your sales. "
                    f"Your typical sales range from MWK {result['lower_bound']:,.0f} to MWK {result['upper_bound']:,.0f}."
                )
            
            return {
                'is_outlier': True,
                'warning_message': warning_message,
                'typical_range': (result['lower_bound'], result['upper_bound']),
                'median': median,
                'confidence': result['confidence'],
                'suggested_value': median,
                'direction': result['direction']
            }
        
        return {
            'is_outlier': False,
            'warning_message': None,
            'typical_range': (result['lower_bound'], result['upper_bound']),
            'confidence': result['confidence']
        }
    
    def check_stock_quantity(
        self,
        quantity: Decimal,
        product_name: Optional[str] = None
    ) -> Dict:
        """
        Check if a stock-in quantity is unusual.
        
        Args:
            quantity: The quantity being added
            product_name: Optional product name for product-specific analysis
        
        Returns:
            Dict with outlier detection results
        """
        from inventory.models_unique_products import UniqueProductStockIn
        
        recent_stockins = UniqueProductStockIn.objects.filter(
            business=self.business,
            added_at__gte=self.start_date
        )
        
        if product_name:
            recent_stockins = recent_stockins.filter(product__name__icontains=product_name)
        
        quantities = [float(si.quantity) for si in recent_stockins]
        
        if len(quantities) < 3:
            return {
                'is_outlier': False,
                'warning_message': None,
                'typical_range': None,
                'confidence': 'low',
                'reason': 'Insufficient historical data'
            }
        
        result = self._analyze_outlier(float(quantity), quantities)
        
        if result['is_outlier']:
            if result['direction'] == 'high':
                warning_message = (
                    f"This quantity ({quantity:,.0f}) is unusually high. "
                    f"You typically add between {result['lower_bound']:,.0f} and {result['upper_bound']:,.0f} items. "
                    f"Are you sure this is correct?"
                )
            else:
                warning_message = (
                    f"This quantity ({quantity:,.0f}) is lower than usual. "
                    f"You typically add between {result['lower_bound']:,.0f} and {result['upper_bound']:,.0f} items."
                )
            
            return {
                'is_outlier': True,
                'warning_message': warning_message,
                'typical_range': (result['lower_bound'], result['upper_bound']),
                'median': result['median'],
                'confidence': result['confidence'],
                'direction': result['direction']
            }
        
        return {
            'is_outlier': False,
            'warning_message': None,
            'typical_range': (result['lower_bound'], result['upper_bound']),
            'confidence': result['confidence']
        }
    
    def check_price(
        self,
        price: Decimal,
        price_type: str = 'selling',  # 'selling' or 'cost'
        vertical: Optional[str] = None
    ) -> Dict:
        """
        Check if a price is unusual.
        
        Args:
            price: The price to check
            price_type: 'selling' or 'cost'
            vertical: Optional vertical for context
        
        Returns:
            Dict with outlier detection results
        """
        from inventory.models_unique_products import UniqueProduct
        
        products = UniqueProduct.objects.filter(
            business=self.business,
            is_active=True
        )
        
        if vertical:
            products = products.filter(vertical=vertical)
        
        if price_type == 'selling':
            prices = [float(p.selling_price) for p in products if p.selling_price]
        else:
            prices = [float(p.cost_price) for p in products if p.cost_price]
        
        if len(prices) < 3:
            return {
                'is_outlier': False,
                'warning_message': None,
                'confidence': 'low',
                'reason': 'Insufficient pricing data'
            }
        
        result = self._analyze_outlier(float(price), prices)
        
        if result['is_outlier']:
            price_label = 'Selling price' if price_type == 'selling' else 'Cost price'
            
            if result['direction'] == 'high':
                warning_message = (
                    f"{price_label} of MWK {price:,.0f} is higher than usual. "
                    f"Your typical {price_type} prices range from MWK {result['lower_bound']:,.0f} to MWK {result['upper_bound']:,.0f}."
                )
            else:
                warning_message = (
                    f"{price_label} of MWK {price:,.0f} is lower than usual. "
                    f"Your typical {price_type} prices range from MWK {result['lower_bound']:,.0f} to MWK {result['upper_bound']:,.0f}."
                )
            
            return {
                'is_outlier': True,
                'warning_message': warning_message,
                'typical_range': (result['lower_bound'], result['upper_bound']),
                'confidence': result['confidence'],
                'direction': result['direction']
            }
        
        return {
            'is_outlier': False,
            'warning_message': None,
            'confidence': result['confidence']
        }
    
    def _analyze_outlier(
        self,
        value: float,
        historical_values: List[float]
    ) -> Dict:
        """
        Internal method to perform statistical outlier detection.
        Uses IQR (Interquartile Range) method - robust to extreme values.
        
        Args:
            value: Value to check
            historical_values: List of historical values
        
        Returns:
            Dict with analysis results
        """
        if len(historical_values) < 3:
            return {
                'is_outlier': False,
                'confidence': 'low',
                'median': 0,
                'iqr': 0,
                'lower_bound': 0,
                'upper_bound': 0
            }
        
        # Sort values
        sorted_values = sorted(historical_values)
        
        # Calculate quartiles
        q1 = self._percentile(sorted_values, 25)
        median = self._percentile(sorted_values, 50)
        q3 = self._percentile(sorted_values, 75)
        
        # IQR (Interquartile Range)
        iqr = q3 - q1
        
        # Outlier boundaries (using 1.5 * IQR - standard threshold)
        lower_bound = q1 - (1.5 * iqr)
        upper_bound = q3 + (1.5 * iqr)
        
        # Determine if outlier
        is_outlier = value < lower_bound or value > upper_bound
        
        # Confidence based on sample size
        if len(historical_values) >= 30:
            confidence = 'high'
        elif len(historical_values) >= 10:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        # Direction
        if value > upper_bound:
            direction = 'high'
        elif value < lower_bound:
            direction = 'low'
        else:
            direction = 'normal'
        
        return {
            'is_outlier': is_outlier,
            'median': median,
            'iqr': iqr,
            'lower_bound': max(0, lower_bound),  # Can't be negative
            'upper_bound': upper_bound,
            'confidence': confidence,
            'direction': direction,
            'sample_size': len(historical_values)
        }
    
    @staticmethod
    def _percentile(sorted_values: List[float], percentile: float) -> float:
        """
        Calculate percentile of sorted values.
        
        Args:
            sorted_values: List of sorted values
            percentile: Percentile to calculate (0-100)
        
        Returns:
            Percentile value
        """
        if not sorted_values:
            return 0
        
        if len(sorted_values) == 1:
            return sorted_values[0]
        
        index = (len(sorted_values) - 1) * (percentile / 100.0)
        floor_index = int(index)
        ceil_index = min(floor_index + 1, len(sorted_values) - 1)
        
        if floor_index == ceil_index:
            return sorted_values[floor_index]
        
        # Linear interpolation
        lower_value = sorted_values[floor_index]
        upper_value = sorted_values[ceil_index]
        fraction = index - floor_index
        
        return lower_value + (upper_value - lower_value) * fraction


def check_value_outlier(
    business,
    value: Decimal,
    check_type: str,  # 'sale', 'stock_quantity', 'selling_price', 'cost_price'
    **kwargs
) -> Dict:
    """
    Convenience function to check for outliers.
    
    Args:
        business: Business object
        value: Value to check
        check_type: Type of check to perform
        **kwargs: Additional context (vertical, product_name, etc.)
    
    Returns:
        Dict with outlier detection results
    """
    detector = OutlierDetector(business, lookback_days=30)
    
    if check_type == 'sale':
        return detector.check_sale_amount(value, vertical=kwargs.get('vertical'))
    elif check_type == 'stock_quantity':
        return detector.check_stock_quantity(value, product_name=kwargs.get('product_name'))
    elif check_type == 'selling_price':
        return detector.check_price(value, price_type='selling', vertical=kwargs.get('vertical'))
    elif check_type == 'cost_price':
        return detector.check_price(value, price_type='cost', vertical=kwargs.get('vertical'))
    else:
        return {
            'is_outlier': False,
            'warning_message': None,
            'confidence': 'low',
            'reason': 'Unknown check type'
        }

