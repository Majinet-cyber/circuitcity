# inventory/templatetags/rollback_helpers.py
"""
Template Tags for Rollback Functionality
=========================================
Helpers for showing/hiding rollback buttons based on permissions.
"""
from django import template

register = template.Library()


@register.simple_tag
def can_rollback_sale(sale, user, business):
    """
    Check if user can rollback a sale.
    Uses RollbackService for consistent permission checking.

    Rules:
    - Only Managers (and HQ/Superuser) can roll back sales
    - Managers can roll back ANY sale in their business
    - Agents cannot roll back (even their own sales)

    Usage in template:
        {% can_rollback_sale sale request.user business as can_rollback %}
        {% if can_rollback %}
            <button>Rollback</button>
        {% endif %}
    """
    try:
        # For vertical-specific sales (ClothingSale, PharmacySale, etc.), use Sale model if available
        # Otherwise check directly on the sale object
        from sales.services.rollback import RollbackService
        from sales.models import Sale

        # Check if already rolled back using helper method
        if isinstance(sale, Sale) and RollbackService.is_already_rolled_back(sale):
            return False
        elif hasattr(sale, "is_rolled_back") and sale.is_rolled_back:
            return False

        # Try to convert to Sale object if it's a vertical-specific sale
        if hasattr(sale, "pk") and not isinstance(sale, Sale):
            # For vertical sales, use centralized role system
            from tenants.utils_roles import is_manager, is_agent

            # Superuser/HQ can always rollback
            if hasattr(user, "is_superuser") and user.is_superuser:
                return True
            if hasattr(user, "is_staff") and user.is_staff:
                return True

            # Managers can rollback any sale in their business
            if is_manager(user, business):
                return True

            # Agents cannot rollback
            if is_agent(user, business):
                return False

            # No role found
            return False
        else:
            # Use RollbackService for Sale objects (handles all permission logic)
            can_rollback, error_msg = RollbackService.can_rollback(sale, user, business)
            return can_rollback

    except Exception as e:
        # Fallback: basic check for managers using centralized role system
        try:
            from tenants.utils_roles import is_manager

            # Check if already rolled back using helper method
            if isinstance(sale, Sale) and RollbackService.is_already_rolled_back(sale):
                return False
            elif hasattr(sale, "is_rolled_back") and sale.is_rolled_back:
                return False

            # Superuser/HQ can always rollback
            if hasattr(user, "is_superuser") and user.is_superuser:
                return True
            if hasattr(user, "is_staff") and user.is_staff:
                return True

            # Managers can rollback
            if is_manager(user, business):
                return True
        except:
            pass
        return False


@register.simple_tag
def rollback_button_label(sale):
    """
    Get appropriate label for rollback button.

    Returns:
        - "Already Rolled Back" if rolled back
        - "Rollback Sale" otherwise
    """
    if hasattr(sale, "is_rolled_back") and sale.is_rolled_back:
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
    if hasattr(sale, "is_rolled_back") and sale.is_rolled_back:
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


@register.inclusion_tag("inventory/partials/rollback_button.html")
def rollback_button(sale, user, business, vertical="phones"):
    """
    Render a rollback button with proper permissions and styling.

    Usage:
        {% rollback_button sale request.user business "phones" %}
    """
    can_rollback = can_rollback_sale(sale, user, business)
    already_rolled_back = hasattr(sale, "is_rolled_back") and sale.is_rolled_back

    # Determine URLs based on vertical
    url_map = {
        "phones": "sales:rollback_confirm",
        "liquor": "verticals:liquor_rollback_sale",  # Direct rollback endpoint
        "clothing": "verticals:clothing_rollback_sale",  # Direct rollback endpoint (needs to be created)
        "pharmacy": "verticals:pharmacy_rollback_sale",
        "cosmetics": "verticals:pharmacy_rollback_sale",  # Cosmetics uses pharmacy rollback
        "groceries": "groceries:rollback_sale",  # Groceries-specific rollback
    }

    return {
        "sale": sale,
        "can_rollback": can_rollback,
        "already_rolled_back": already_rolled_back,
        "button_label": rollback_button_label(sale),
        "button_class": rollback_button_class(sale),
        "rollback_url": url_map.get(vertical, "sales:rollback_confirm"),
    }
