"""
Django template filters for universal numeric formatting
Use these in templates to ensure consistent, mobile-first number display
"""

from django import template
from django.utils.safestring import mark_safe
from common.utils.number_formatter import (
    format_money,
    format_compact_number,
    format_number_with_tooltip,
    format_percentage,
    format_unit_value,
    should_compact
)

register = template.Library()


@register.filter(name='money')
def money_filter(value, currency='MWK'):
    """
    Format as money with currency.
    Usage: {{ value|money }} or {{ value|money:"USD" }}
    """
    return format_money(value, currency=currency, compact=False, show_decimals=False)


@register.filter(name='money_compact')
def money_compact_filter(value, currency='MWK'):
    """
    Format as compact money (355k, 2.4m).
    Usage: {{ value|money_compact }} or {{ value|money_compact:"USD" }}
    """
    return format_money(value, currency=currency, compact=True, show_decimals=True)


@register.filter(name='money_tooltip')
def money_tooltip_filter(value, currency='MWK'):
    """
    Format as money with tooltip showing full value if compacted.
    Usage: {{ value|money_tooltip }} or {{ value|money_tooltip:"USD" }}
    """
    return mark_safe(format_number_with_tooltip(value, currency=currency))


@register.filter(name='num_compact')
def num_compact_filter(value):
    """
    Format number in compact notation (k, m, b).
    Usage: {{ value|num_compact }}
    """
    return format_compact_number(value)


@register.filter(name='num_tooltip')
def num_tooltip_filter(value):
    """
    Format number with tooltip if large.
    Usage: {{ value|num_tooltip }}
    """
    return mark_safe(format_number_with_tooltip(value, compact_threshold=100000))


@register.filter(name='percentage')
def percentage_filter(value, decimal_places=1):
    """
    Format as percentage.
    Usage: {{ value|percentage }} or {{ value|percentage:2 }}
    """
    try:
        decimal_places = int(decimal_places)
    except (ValueError, TypeError):
        decimal_places = 1
    return format_percentage(value, decimal_places=decimal_places)


@register.filter(name='unit')
def unit_filter(value, unit):
    """
    Format number with unit.
    Usage: {{ value|unit:"kg" }}
    """
    return format_unit_value(value, unit=unit, compact=False)


@register.filter(name='unit_compact')
def unit_compact_filter(value, unit):
    """
    Format number with unit in compact notation.
    Usage: {{ value|unit_compact:"kg" }}
    """
    return format_unit_value(value, unit=unit, compact=True)


@register.filter(name='intcomma_safe')
def intcomma_safe_filter(value):
    """
    Format with thousands separator, safe for None values.
    Usage: {{ value|intcomma_safe }}
    """
    if value is None:
        return "0"
    try:
        return f"{int(float(value)):,}"
    except (ValueError, TypeError):
        return "0"


@register.simple_tag
def format_kpi_value(value, currency='MWK', compact_threshold=100000):
    """
    Format KPI value with optimal display strategy.
    Usage: {% format_kpi_value revenue "MWK" 100000 %}
    """
    if value is None:
        return f"{currency} 0"
    
    try:
        value = float(value)
    except (ValueError, TypeError):
        return f"{currency} 0"
    
    # If value is below threshold, show full
    if abs(value) < compact_threshold:
        return format_money(value, currency=currency, compact=False)
    
    # Otherwise show with tooltip
    return mark_safe(format_number_with_tooltip(value, compact_threshold=compact_threshold, currency=currency))


@register.simple_tag
def render_money_stack(value, label, currency='MWK', css_class=''):
    """
    Render money value with label in vertical stack.
    Usage: {% render_money_stack revenue "Revenue" "MWK" "num-revenue" %}
    """
    formatted_value = format_money(value, currency=currency, compact=False)
    
    return mark_safe(f'''
        <div class="num-stack {css_class}">
            <div class="stat-label">{label}</div>
            <div class="stat-value num-value">{formatted_value}</div>
        </div>
    ''')


@register.simple_tag
def render_kpi_card(value, label, icon, color_class, currency='MWK'):
    """
    Render a complete KPI card with glassmorphic design.
    Usage: {% render_kpi_card revenue "Revenue" "💵" "num-revenue" "MWK" %}
    """
    formatted_value = format_money(value, currency=currency, compact=False)
    
    return mark_safe(f'''
        <div class="kpi-card-glass {color_class}">
            <div class="kpi-label-glass">
                <span class="kpi-icon-glass">{icon}</span>
                <span>{label}</span>
            </div>
            <div class="kpi-value-glass num-value">{formatted_value}</div>
        </div>
    ''')


@register.filter(name='num_color_class')
def num_color_class_filter(value, metric_type):
    """
    Get semantic color class based on metric type and value.
    Usage: {{ value|num_color_class:"profit" }}
    """
    metric_colors = {
        'revenue': 'num-revenue',
        'profit': 'num-profit',
        'cost': 'num-cost',
        'cogs': 'num-cost',
        'stock': 'num-stock',
        'stock_value': 'num-stock',
    }
    
    return metric_colors.get(metric_type.lower(), 'num-neutral')


@register.inclusion_tag('partials/numeric_display.html')
def numeric_display(value, label=None, unit=None, currency=None, compact=False):
    """
    Render numeric value with optimal formatting.
    Usage: {% numeric_display revenue label="Revenue" currency="MWK" %}
    """
    if currency:
        formatted = format_money(value, currency=currency, compact=compact)
    elif unit:
        formatted = format_unit_value(value, unit=unit, compact=compact)
    else:
        if compact:
            formatted = format_compact_number(value)
        else:
            formatted = f"{int(float(value or 0)):,}"
    
    return {
        'value': formatted,
        'label': label,
        'raw_value': value,
    }

