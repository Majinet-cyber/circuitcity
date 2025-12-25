# inventory/templatetags/rollback_helpers.py
"""
Template Tags for Rollback Functionality
=========================================
Helpers for showing/hiding rollback buttons based on permissions.
"""
from django import template
from datetime import timedelta
from django.utils import timezone

register = template.Library()


@register.simple_tag
def can_rollback_sale(sale, user, business):
    """
    Check if user can rollback a sale.
    
    Usage in template:
        {% can_rollback_sale sale request.user business as can_rollback %}
        {% if can_rollback %}
            <button>Rollback</button>
        {% endif %}
    """
    try:
        # Check if already rolled back
        if hasattr(sale, 'is_rolled_back') and sale.is_rolled_back:
            return False
        
        # Check user membership
        from tenants.models import Membership
        
        try:
            membership = Membership.objects.get(user=user, business=business)
            role = membership.role.upper()
            
            # CRITICAL: Managers, Owners, and Admins can rollback ANY sale IMMEDIATELY
            # No time restrictions, no ownership checks - full operational control
            if role in ["MANAGER", "OWNER", "ADMIN", "HQ_ADMIN"]:
                return True
            
            # Agents can only rollback their own sales within 10 minutes
            if role == "AGENT":
                # Check if it's their sale
                sale_agent = getattr(sale, 'agent', None) or getattr(sale, 'sold_by', None)
                if sale_agent != user:
                    return False
                
                # Check timing
                sale_time = getattr(sale, 'created_at', None) or getattr(sale, 'sold_at', None)
                if sale_time:
                    time_since_sale = timezone.now() - sale_time
                    if time_since_sale > timedelta(minutes=10):
                        return False
                
                return True
            
            return False
        
        except Membership.DoesNotExist:
            return False
    
    except Exception:
        return False


@register.simple_tag
def rollback_button_label(sale):
    """
    Get appropriate label for rollback button.
    
    Returns:
        - "Already Rolled Back" if rolled back
        - "Rollback Sale" otherwise
    """
    if hasattr(sale, 'is_rolled_back') and sale.is_rolled_back:
        return "Already Rolled Back"
    return "Rollback Sale"


@register.simple_tag
def rollback_button_class(sale):
    """
    Get appropriate CSS class for rollback button.
    
    Returns:
        - "btn-secondary disabled" if rolled back
        - "btn-danger" otherwise
    """
    if hasattr(sale, 'is_rolled_back') and sale.is_rolled_back:
        return "btn-secondary disabled"
    return "btn-danger"


@register.filter
def format_currency(value, currency="MK"):
    """
    Format a number as currency with thousand separators.
    
    Usage:
        {{ sale.price|format_currency }}
        {{ sale.price|format_currency:"USD" }}
    """
    try:
        from decimal import Decimal
        if isinstance(value, (int, float, Decimal)):
            return f"{currency} {value:,.2f}"
        return f"{currency} {value}"
    except Exception:
        return f"{currency} {value}"


@register.filter
def format_number(value):
    """
    Format a number with thousand separators.
    
    Usage:
        {{ quantity|format_number }}
    """
    try:
        return f"{value:,}"
    except Exception:
        return str(value)


@register.simple_tag
def get_rollback_reason_display(reason):
    """
    Get human-readable rollback reason.
    
    Usage:
        {% get_rollback_reason_display sale.rollback_reason as reason_text %}
    """
    reasons = {
        "DAMAGED": "Damaged Product",
        "RETURNED": "Customer Return",
        "ERROR": "Data Entry Error",
        "OTHER": "Other Reason",
    }
    return reasons.get(reason, reason)


@register.inclusion_tag('inventory/partials/rollback_button.html')
def rollback_button(sale, user, business, vertical="phones"):
    """
    Render a rollback button with proper permissions and styling.
    
    Usage:
        {% rollback_button sale request.user business "phones" %}
    """
    can_rollback = can_rollback_sale(sale, user, business)
    already_rolled_back = hasattr(sale, 'is_rolled_back') and sale.is_rolled_back
    
    # Determine URLs based on vertical
    url_map = {
        "phones": "sales:rollback_confirm",
        "liquor": "liquor:rollback_confirm",
        "clothing": "clothing:rollback_confirm",
    }
    
    return {
        'sale': sale,
        'can_rollback': can_rollback,
        'already_rolled_back': already_rolled_back,
        'button_label': rollback_button_label(sale),
        'button_class': rollback_button_class(sale),
        'rollback_url': url_map.get(vertical, "sales:rollback_confirm"),
    }

