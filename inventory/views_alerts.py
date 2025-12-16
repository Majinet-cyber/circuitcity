# inventory/views_alerts.py
"""
Views for alerts/notifications system.
"""
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, get_object_or_404
from django.contrib import messages

from inventory.decorators import require_business
from inventory import base
from inventory.models_alerts import Alert


@login_required
@require_business
@require_http_methods(["GET"])
def alerts_list_json(request):
    """
    JSON endpoint for alerts list.
    Returns unread and recent alerts for the business.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if not business:
        return JsonResponse({"error": "No business selected"}, status=400)
    
    # Get filters
    show_read = request.GET.get('show_read', 'false').lower() == 'true'
    alert_type = request.GET.get('type', '')
    limit = int(request.GET.get('limit', 20))
    
    # Build queryset
    alerts_qs = Alert.objects.filter(business=business, is_dismissed=False)
    
    if not show_read:
        alerts_qs = alerts_qs.filter(is_read=False)
    
    if alert_type:
        alerts_qs = alerts_qs.filter(alert_type=alert_type)
    
    alerts_qs = alerts_qs[:limit]
    
    # Serialize alerts
    alerts_data = []
    for alert in alerts_qs:
        alerts_data.append({
            'id': alert.id,
            'type': alert.alert_type,
            'type_display': alert.get_alert_type_display(),
            'priority': alert.priority,
            'title': alert.title,
            'message': alert.message,
            'is_read': alert.is_read,
            'created_at': alert.created_at.isoformat(),
            'meta': alert.meta,
        })
    
    # Get counts
    unread_count = Alert.objects.filter(business=business, is_read=False, is_dismissed=False).count()
    
    return JsonResponse({
        'ok': True,
        'alerts': alerts_data,
        'unread_count': unread_count,
        'total_shown': len(alerts_data),
    })


@login_required
@require_business
@require_http_methods(["POST"])
def alert_mark_read(request, alert_id):
    """Mark an alert as read."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    alert = get_object_or_404(Alert, id=alert_id, business=business)
    alert.mark_as_read()
    
    return JsonResponse({'ok': True, 'alert_id': alert_id})


@login_required
@require_business
@require_http_methods(["POST"])
def alert_dismiss(request, alert_id):
    """Dismiss an alert."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    alert = get_object_or_404(Alert, id=alert_id, business=business)
    alert.is_dismissed = True
    alert.save(update_fields=['is_dismissed'])
    
    return JsonResponse({'ok': True, 'alert_id': alert_id})


@login_required
@require_business
@require_http_methods(["POST"])
def alerts_mark_all_read(request):
    """Mark all alerts as read for this business."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    count = Alert.objects.filter(
        business=business,
        is_read=False,
        is_dismissed=False,
    ).update(is_read=True)
    
    return JsonResponse({'ok': True, 'marked_count': count})


@login_required
@require_business
def alerts_page(request):
    """
    Full alerts page showing all alerts for the business.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Get filter params
    show_read = request.GET.get('show_read', 'false').lower() == 'true'
    alert_type = request.GET.get('type', '')
    
    # Build queryset
    alerts_qs = Alert.objects.filter(business=business, is_dismissed=False)
    
    if not show_read:
        alerts_qs = alerts_qs.filter(is_read=False)
    
    if alert_type:
        alerts_qs = alerts_qs.filter(alert_type=alert_type)
    
    alerts = alerts_qs[:50]  # Limit to 50 for page load
    
    return render(request, 'inventory/alerts.html', {
        **ctx,
        'alerts': alerts,
        'show_read': show_read,
        'alert_type': alert_type,
        'page_title': 'Alerts & Notifications',
    })

