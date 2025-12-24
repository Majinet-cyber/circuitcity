# inventory/utils_pricing.py
"""
Pricing Validation Utilities
=============================
Real-time price validation with smart suggestions and warnings.
Used by ALL verticals (Phones, Liquor, Pharmacy, etc.) for consistent pricing intelligence.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, Optional
import re


def detect_magnitude_error(selling_price: Decimal, order_price: Decimal) -> Optional[Dict[str, Any]]:
    """
    Detect if user typed wrong magnitude (missing zeros, extra zeros, decimal errors).
    
    Examples:
        Order: 31,500 → User typed: 888 → Should be: 88,800 or 8,880?
        Order: 50,000 → User typed: 5000 → Should be: 50,000?
    
    Returns dict with 'detected', 'suggestions' if error found, else None.
    """
    if not order_price or order_price <= 0:
        return None
    
    # Price is way too low compared to cost (less than 10% of cost)
    if selling_price > 0 and selling_price < (order_price * Decimal("0.10")):
        # Suggest multiplying by 10 or 100
        suggestions = []
        
        multiplied_10 = selling_price * 10
        multiplied_100 = selling_price * 100
        
        # Only suggest if it gets close to reasonable range (0.8x to 2x cost)
        if Decimal("0.8") * order_price <= multiplied_10 <= 2 * order_price:
            suggestions.append(format_currency(multiplied_10))
        
        if Decimal("0.8") * order_price <= multiplied_100 <= 2 * order_price:
            suggestions.append(format_currency(multiplied_100))
        
        if suggestions:
            return {
                "detected": True,
                "suggestions": suggestions,
                "message": f"This looks unusually low. Did you mean {' or '.join(suggestions)}?"
            }
    
    return None


def validate_selling_price(
    selling_price: Decimal,
    cost_price: Optional[Decimal] = None,
    suggested_price: Optional[Decimal] = None,
    product_name: str = ""
) -> Dict[str, Any]:
    """
    Validate selling price with smart warnings and suggestions.
    
    This is the CORE pricing intelligence function used across all verticals.
    
    Returns a dict with:
    - valid: bool (whether price is acceptable)
    - warnings: list of warning messages
    - suggestions: list of suggested corrections
    - profit_margin: Decimal or None
    - profit_margin_pct: Decimal or None
    - feedback: str (positive/negative feedback)
    - severity: str ("error", "warning", "success", "info")
    """
    result = {
        "valid": True,
        "warnings": [],
        "suggestions": [],
        "profit_margin": None,
        "profit_margin_pct": None,
        "feedback": "",
        "severity": "info",
    }
    
    # Basic validation
    if selling_price <= 0:
        result["valid"] = False
        result["warnings"].append("❌ Price must be greater than zero")
        result["severity"] = "error"
        return result
    
    # Check for absurdly high prices (likely data entry error)
    if selling_price > Decimal("100000000"):  # 100 million
        result["valid"] = False
        result["warnings"].append("❌ Price is unreasonably high. Please check your input.")
        result["severity"] = "error"
        return result
    
    # Check for suspiciously high prices
    if selling_price > Decimal("10000000"):  # 10 million
        result["warnings"].append("⚠️ This price looks unusually high. Please confirm.")
        result["severity"] = "warning"
    
    # Cost-based validation (PRIMARY INTELLIGENCE)
    if cost_price and cost_price > 0:
        profit_margin = selling_price - cost_price
        profit_margin_pct = (profit_margin / cost_price) * 100
        
        result["profit_margin"] = profit_margin
        result["profit_margin_pct"] = profit_margin_pct
        
        # 1. Check for magnitude errors FIRST (most critical)
        magnitude_error = detect_magnitude_error(selling_price, cost_price)
        if magnitude_error:
            result["warnings"].append(magnitude_error["message"])
            result["suggestions"].extend(magnitude_error["suggestions"])
            result["severity"] = "warning"
        
        # 2. Below cost warning (CRITICAL)
        if selling_price < cost_price:
            loss = cost_price - selling_price
            result["warnings"].append(
                f"⚠️ This is below order value ({format_currency(cost_price)})."
            )
            result["suggestions"].append(f"Did you mean {format_currency(cost_price)}?")
            
            # Add reasonable markup suggestions
            markup_10 = cost_price * Decimal("1.10")  # 10% markup
            markup_20 = cost_price * Decimal("1.20")  # 20% markup
            result["suggestions"].append(f"Or {format_currency(markup_10)}?")
            result["suggestions"].append(f"Or {format_currency(markup_20)}?")
            
            result["severity"] = "warning"
        
        # 3. Very low margin warning (< 5%)
        elif profit_margin_pct < 5:
            result["warnings"].append(
                f"⚠️ Low profit margin ({profit_margin_pct:.1f}%). Consider pricing higher."
            )
            result["severity"] = "warning"
        
        # 4. Good margin feedback (>= 10%)
        elif profit_margin_pct >= 15:
            result["feedback"] = f"✅ Great profit margin ({profit_margin_pct:.1f}%)!"
            result["severity"] = "success"
        elif profit_margin_pct >= 10:
            result["feedback"] = f"✅ Good profit margin ({profit_margin_pct:.1f}%)"
            result["severity"] = "success"
        else:
            result["feedback"] = f"Profit margin: {profit_margin_pct:.1f}%"
            result["severity"] = "info"
    
    # Suggested price comparison (if available)
    if suggested_price and suggested_price > 0 and cost_price:
        diff = selling_price - suggested_price
        diff_pct = (diff / suggested_price) * 100
        
        # Only warn if deviation is significant AND different from cost-based feedback
        if abs(diff_pct) > 30:
            if diff > 0:
                result["warnings"].append(
                    f"⚠️ Price is {diff_pct:.0f}% higher than typical ({format_currency(suggested_price)})"
                )
            else:
                result["warnings"].append(
                    f"⚠️ Price is {abs(diff_pct):.0f}% lower than typical ({format_currency(suggested_price)})"
                )
            
            if result["severity"] == "info":
                result["severity"] = "warning"
    
    return result


def format_currency(amount: Decimal, currency: str = "MK") -> str:
    """
    Format currency with thousands separators.
    
    Examples:
        2000000 -> "MK 2,000,000"
        1500.50 -> "MK 1,500.50"
        31500 -> "MK 31,500"
    """
    try:
        # Round to 2 decimal places but strip unnecessary zeros
        formatted = f"{float(amount):,.2f}".rstrip('0').rstrip('.')
        return f"{currency} {formatted}"
    except Exception:
        return f"{currency} {amount}"


def format_number(number: int) -> str:
    """
    Format number with thousands separators.
    
    Examples:
        2000000 -> "2,000,000"
        1500 -> "1,500"
    """
    try:
        return f"{number:,}"
    except Exception:
        return str(number)


def parse_currency_input(input_str: str) -> Decimal:
    """
    Parse currency input, removing commas and currency symbols.
    
    Examples:
        "MK 2,000,000" -> Decimal("2000000")
        "1,500.50" -> Decimal("1500.50")
        "2000000" -> Decimal("2000000")
        "31,500" -> Decimal("31500")
    """
    if not input_str:
        return Decimal("0")
    
    # Remove common currency symbols and commas
    cleaned = str(input_str).replace(",", "").replace("MK", "").replace("K", "").strip()
    
    try:
        return Decimal(cleaned)
    except Exception:
        return Decimal("0")


def get_pricing_intelligence_json(
    selling_price: Decimal,
    cost_price: Optional[Decimal] = None,
    suggested_price: Optional[Decimal] = None
) -> Dict[str, Any]:
    """
    Get pricing intelligence as JSON-friendly dict (for API responses).
    
    Used by: AJAX validation endpoints, real-time feedback APIs.
    """
    validation = validate_selling_price(selling_price, cost_price, suggested_price)
    
    return {
        "ok": validation["valid"],
        "severity": validation["severity"],
        "warnings": validation["warnings"],
        "suggestions": validation["suggestions"],
        "feedback": validation["feedback"],
        "profit_margin": float(validation["profit_margin"]) if validation["profit_margin"] else None,
        "profit_margin_pct": float(validation["profit_margin_pct"]) if validation["profit_margin_pct"] else None,
    }


def format_currency(amount: Decimal, currency: str = "MK") -> str:
    """
    Format currency with thousands separators.
    
    Examples:
        2000000 -> "MK 2,000,000"
        1500.50 -> "MK 1,500.50"
    """
    try:
        return f"{currency} {amount:,.2f}"
    except Exception:
        return f"{currency} {amount}"


def format_number(number: int) -> str:
    """
    Format number with thousands separators.
    
    Examples:
        2000000 -> "2,000,000"
        1500 -> "1,500"
    """
    try:
        return f"{number:,}"
    except Exception:
        return str(number)


def parse_currency_input(input_str: str) -> Decimal:
    """
    Parse currency input, removing commas and currency symbols.
    
    Examples:
        "MK 2,000,000" -> Decimal("2000000")
        "1,500.50" -> Decimal("1500.50")
        "2000000" -> Decimal("2000000")
    """
    if not input_str:
        return Decimal("0")
    
    # Remove common currency symbols and commas
    cleaned = input_str.replace(",", "").replace("MK", "").replace("K", "").strip()
    
    try:
        return Decimal(cleaned)
    except Exception:
        return Decimal("0")

