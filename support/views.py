# support/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from .models import Ticket, TicketComment
from .forms import TicketCreateForm, TicketUpdateForm, TicketCommentForm
from tenants.utils import get_active_business
from tenants.decorators import manager_only, hq_only


@login_required
@manager_only
def manager_ticket_list(request):
    """Manager view: list their business's tickets."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No business selected.")
        return redirect('tenants:choose_business')
    
    tickets = Ticket.objects.filter(business=business).select_related(
        'creator', 'assigned_to', 'resolved_by'
    )
    
    # Filter by status if requested
    status_filter = request.GET.get('status')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    
    paginator = Paginator(tickets, 20)
    page = request.GET.get('page', 1)
    tickets_page = paginator.get_page(page)
    
    return render(request, 'support/manager_ticket_list.html', {
        'tickets': tickets_page,
        'status_choices': Ticket.STATUS_CHOICES,
        'current_status': status_filter,
    })


@login_required
@manager_only
def manager_ticket_create(request):
    """Manager view: create a new ticket."""
    business = get_active_business(request)
    if not business:
        messages.error(request, "No business selected.")
        return redirect('tenants:choose_business')
    
    if request.method == 'POST':
        form = TicketCreateForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.business = business
            ticket.creator = request.user
            ticket.save()
            
            messages.success(request, f"Ticket {ticket.reference} created successfully.")
            return redirect('support:manager_ticket_detail', pk=ticket.pk)
    else:
        form = TicketCreateForm()
    
    return render(request, 'support/manager_ticket_create.html', {
        'form': form,
    })


@login_required
def manager_ticket_detail(request, pk):
    """Manager view: view ticket details and add comments."""
    business = get_active_business(request)
    
    # Managers can only see their business's tickets
    if not (request.user.is_staff or request.user.is_superuser):
        ticket = get_object_or_404(Ticket, pk=pk, business=business)
    else:
        ticket = get_object_or_404(Ticket, pk=pk)
    
    # Handle comment submission
    if request.method == 'POST':
        form = TicketCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.ticket = ticket
            comment.author = request.user
            # Managers cannot create internal comments
            if not (request.user.is_staff or request.user.is_superuser):
                comment.is_internal = False
            comment.save()
            
            messages.success(request, "Comment added.")
            return redirect('support:manager_ticket_detail', pk=ticket.pk)
    else:
        form = TicketCommentForm()
    
    # Filter comments: managers don't see internal notes
    comments = ticket.comments.select_related('author')
    if not (request.user.is_staff or request.user.is_superuser):
        comments = comments.filter(is_internal=False)
    
    return render(request, 'support/manager_ticket_detail.html', {
        'ticket': ticket,
        'comments': comments,
        'form': form,
    })


@login_required
@hq_only
def hq_ticket_list(request):
    """HQ view: list all tickets with filters."""
    tickets = Ticket.objects.all().select_related(
        'business', 'creator', 'assigned_to', 'resolved_by'
    )
    
    # Filters
    status_filter = request.GET.get('status')
    if status_filter:
        tickets = tickets.filter(status=status_filter)
    
    business_filter = request.GET.get('business')
    if business_filter:
        tickets = tickets.filter(business_id=business_filter)
    
    priority_filter = request.GET.get('priority')
    if priority_filter:
        tickets = tickets.filter(priority=priority_filter)
    
    search = request.GET.get('search')
    if search:
        tickets = tickets.filter(
            Q(reference__icontains=search) |
            Q(subject__icontains=search) |
            Q(description__icontains=search)
        )
    
    paginator = Paginator(tickets, 25)
    page = request.GET.get('page', 1)
    tickets_page = paginator.get_page(page)
    
    # Get business list for filter
    from tenants.models import Business
    businesses = Business.objects.filter(status='ACTIVE').order_by('name')
    
    return render(request, 'support/hq_ticket_list.html', {
        'tickets': tickets_page,
        'status_choices': Ticket.STATUS_CHOICES,
        'priority_choices': Ticket.PRIORITY_CHOICES,
        'businesses': businesses,
        'current_status': status_filter,
        'current_business': business_filter,
        'current_priority': priority_filter,
        'search_query': search,
    })


@login_required
@hq_only
def hq_ticket_detail(request, pk):
    """HQ view: ticket detail with update capabilities."""
    ticket = get_object_or_404(Ticket, pk=pk)
    
    # Handle status update
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            form = TicketUpdateForm(request.POST, instance=ticket)
            if form.is_valid():
                updated_ticket = form.save(commit=False)
                if updated_ticket.status in ['RESOLVED', 'CLOSED']:
                    updated_ticket.resolved_by = request.user
                updated_ticket.save()
                messages.success(request, "Ticket updated.")
                return redirect('support:hq_ticket_detail', pk=ticket.pk)
        
        elif action == 'add_comment':
            comment_form = TicketCommentForm(request.POST)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.ticket = ticket
                comment.author = request.user
                comment.save()
                messages.success(request, "Comment added.")
                return redirect('support:hq_ticket_detail', pk=ticket.pk)
    
    update_form = TicketUpdateForm(instance=ticket)
    comment_form = TicketCommentForm()
    comments = ticket.comments.select_related('author').all()
    
    return render(request, 'support/hq_ticket_detail.html', {
        'ticket': ticket,
        'update_form': update_form,
        'comment_form': comment_form,
        'comments': comments,
    })

