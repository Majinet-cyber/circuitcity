# notifications/views.py
"""
Views for managing user notifications.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.paginator import Paginator
from .models import Notification


@login_required
def notification_list(request):
    """Full page listing all notifications for the current user."""
    notifications = Notification.objects.filter(user=request.user)
    
    # Filter by read/unread
    filter_type = request.GET.get('filter', 'all')
    if filter_type == 'unread':
        notifications = notifications.filter(read_at__isnull=True)
    elif filter_type == 'read':
        notifications = notifications.filter(read_at__isnull=False)
    
    paginator = Paginator(notifications, 20)
    page = request.GET.get('page', 1)
    notifications_page = paginator.get_page(page)
    
    return render(request, 'notifications/notification_list.html', {
        'notifications': notifications_page,
        'filter_type': filter_type,
    })


@login_required
def notification_dropdown(request):
    """API endpoint for the notification dropdown (latest 10)."""
    notifications = Notification.objects.filter(user=request.user)[:10]
    unread_count = Notification.objects.filter(user=request.user, read_at__isnull=True).count()
    
    data = {
        'unread_count': unread_count,
        'notifications': [
            {
                'id': n.id,
                'message': n.message,
                'level': n.level,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
                'meta': n.meta,
            }
            for n in notifications
        ]
    }
    
    return JsonResponse(data)


@login_required
def mark_as_read(request, pk):
    """Mark a single notification as read."""
    try:
        notification = Notification.objects.get(pk=pk, user=request.user)
        notification.mark_read()
    except Notification.DoesNotExist:
        pass
    
    return redirect(request.META.get('HTTP_REFERER', 'notifications:list'))


@login_required
def mark_all_as_read(request):
    """Mark all user's notifications as read."""
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    
    return redirect('notifications:list')


from django.utils import timezone
