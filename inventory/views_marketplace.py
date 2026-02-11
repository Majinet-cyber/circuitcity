# inventory/views_marketplace.py
"""
Marketplace views for public listings and business pages.

This module provides:
- Public marketplace page showing all active listings
- Public business pages (/public/<business_slug>/)
- Manager UI for creating/editing listings
- Enquiry submission and viewing
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from inventory.models_marketplace import MarketplaceListing, MarketplaceEnquiry
from tenants.models import Business
from tenants.decorators import require_business


# ============================================================================
# PUBLIC VIEWS (No login required)
# ============================================================================

@never_cache
def marketplace_public(request: HttpRequest) -> HttpResponse:
    """
    Public marketplace page showing all active listings from all businesses.
    
    Features:
    - No login required
    - Only shows active listings
    - Paginated (20 per page)
    - Can filter by vertical
    - Mobile-friendly
    """
    # Get filter parameters
    vertical_filter = request.GET.get('vertical', '').strip()
    
    # Query active listings
    listings = MarketplaceListing.objects.filter(is_active=True).select_related('business')
    
    # Apply vertical filter if provided
    if vertical_filter:
        listings = listings.filter(vertical=vertical_filter)
    
    # Order by most recent first
    listings = listings.order_by('-created_at')
    
    # Paginate (20 per page)
    paginator = Paginator(listings, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get unique verticals for filter dropdown
    available_verticals = (
        MarketplaceListing.objects
        .filter(is_active=True)
        .exclude(vertical='')
        .values_list('vertical', flat=True)
        .distinct()
        .order_by('vertical')
    )
    
    return render(request, 'inventory/marketplace_public.html', {
        'page_obj': page_obj,
        'vertical_filter': vertical_filter,
        'available_verticals': available_verticals,
        'hide_nav': True,  # Don't show internal navigation
    })


@never_cache
def business_public_page(request: HttpRequest, business_slug: str) -> HttpResponse:
    """
    Public-facing page for a specific business.
    
    Shows:
    - Business name and logo
    - All active listings from this business
    - Contact/enquiry form for each listing
    
    URL: /public/<business_slug>/
    """
    business = get_object_or_404(Business, slug=business_slug)
    
    # Get active listings for this business
    listings = (
        MarketplaceListing.objects
        .filter(business=business, is_active=True)
        .order_by('-created_at')
    )
    
    # Paginate (12 per page)
    paginator = Paginator(listings, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/business_public_page.html', {
        'business': business,
        'page_obj': page_obj,
        'hide_nav': True,  # Don't show internal navigation
    })


@require_http_methods(['POST'])
def submit_enquiry(request: HttpRequest, listing_id: int) -> HttpResponse:
    """
    Submit an enquiry about a marketplace listing.
    
    Public endpoint (no login required).
    Creates MarketplaceEnquiry record.
    """
    listing = get_object_or_404(MarketplaceListing, id=listing_id, is_active=True)
    
    # Extract form data
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    name = request.POST.get('name', '').strip()
    message = request.POST.get('message', '').strip()
    
    # Validate email (required)
    if not email:
        messages.error(request, "Email is required.")
        return redirect(request.META.get('HTTP_REFERER', '/marketplace/'))
    
    # Create enquiry
    try:
        enquiry = MarketplaceEnquiry.objects.create(
            listing=listing,
            business=listing.business,
            email=email,
            phone=phone,
            name=name,
            message=message,
        )
        
        messages.success(
            request,
            f"Your enquiry has been sent to {listing.business.name}. "
            "They will contact you soon!"
        )
        
        # Redirect back to the page they came from
        return redirect(request.META.get('HTTP_REFERER', '/marketplace/'))
        
    except Exception as e:
        messages.error(request, f"Failed to submit enquiry: {str(e)}")
        return redirect(request.META.get('HTTP_REFERER', '/marketplace/'))


# ============================================================================
# MANAGER VIEWS (Login + business required)
# ============================================================================

@login_required
@require_business
def manage_listings(request: HttpRequest) -> HttpResponse:
    """
    Manager dashboard for marketplace listings.
    
    Shows:
    - List of all listings (active and inactive)
    - Create new listing button
    - Edit/delete actions
    - Unread enquiries count
    
    Permissions: Manager or Admin only
    """
    business = request.active_business
    
    # Get all listings for this business
    listings = (
        MarketplaceListing.objects
        .filter(business=business)
        .order_by('-created_at')
    )
    
    # Get unread enquiries count
    unread_count = MarketplaceEnquiry.objects.filter(
        business=business,
        is_read=False
    ).count()
    
    return render(request, 'inventory/manage_listings.html', {
        'listings': listings,
        'unread_enquiries_count': unread_count,
    })


@login_required
@require_business
@require_http_methods(['GET', 'POST'])
def create_listing(request: HttpRequest) -> HttpResponse:
    """
    Create a new marketplace listing.
    
    Permissions: Manager or Admin only
    """
    business = request.active_business
    
    if request.method == 'POST':
        # Extract form data
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '').strip()
        vertical = request.POST.get('vertical', '').strip()
        media_file = request.FILES.get('media_file')
        
        # Validate required fields
        if not title:
            messages.error(request, "Title is required.")
            return render(request, 'inventory/create_listing.html', {
                'form_data': request.POST,
            })
        
        # Parse price (optional)
        price_decimal = None
        if price:
            try:
                price_decimal = float(price)
            except ValueError:
                messages.error(request, "Invalid price format.")
                return render(request, 'inventory/create_listing.html', {
                    'form_data': request.POST,
                })
        
        # Create listing
        try:
            listing = MarketplaceListing.objects.create(
                business=business,
                title=title,
                description=description,
                price=price_decimal,
                vertical=vertical or business.business_kind or '',
                media_file=media_file,
                created_by=request.user,
            )
            
            messages.success(request, f"Listing '{title}' created successfully!")
            return redirect('inventory:manage_listings')
            
        except Exception as e:
            messages.error(request, f"Failed to create listing: {str(e)}")
            return render(request, 'inventory/create_listing.html', {
                'form_data': request.POST,
            })
    
    # GET request - show form
    return render(request, 'inventory/create_listing.html', {
        'business': business,
    })


@login_required
@require_business
@require_http_methods(['GET', 'POST'])
def edit_listing(request: HttpRequest, listing_id: int) -> HttpResponse:
    """
    Edit an existing marketplace listing.
    
    Permissions: Manager or Admin only
    """
    business = request.active_business
    listing = get_object_or_404(MarketplaceListing, id=listing_id, business=business)
    
    if request.method == 'POST':
        # Extract form data
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        price = request.POST.get('price', '').strip()
        vertical = request.POST.get('vertical', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        media_file = request.FILES.get('media_file')
        
        # Validate required fields
        if not title:
            messages.error(request, "Title is required.")
            return render(request, 'inventory/edit_listing.html', {
                'listing': listing,
            })
        
        # Parse price (optional)
        price_decimal = None
        if price:
            try:
                price_decimal = float(price)
            except ValueError:
                messages.error(request, "Invalid price format.")
                return render(request, 'inventory/edit_listing.html', {
                    'listing': listing,
                })
        
        # Update listing
        try:
            listing.title = title
            listing.description = description
            listing.price = price_decimal
            listing.vertical = vertical
            listing.is_active = is_active
            
            if media_file:
                listing.media_file = media_file
            
            listing.save()
            
            messages.success(request, f"Listing '{title}' updated successfully!")
            return redirect('inventory:manage_listings')
            
        except Exception as e:
            messages.error(request, f"Failed to update listing: {str(e)}")
            return render(request, 'inventory/edit_listing.html', {
                'listing': listing,
            })
    
    # GET request - show form
    return render(request, 'inventory/edit_listing.html', {
        'listing': listing,
    })


@login_required
@require_business
@require_http_methods(['POST'])
def delete_listing(request: HttpRequest, listing_id: int) -> HttpResponse:
    """
    Delete a marketplace listing.
    
    Permissions: Manager or Admin only
    """
    business = request.active_business
    listing = get_object_or_404(MarketplaceListing, id=listing_id, business=business)
    
    title = listing.title
    listing.delete()
    
    messages.success(request, f"Listing '{title}' deleted successfully!")
    return redirect('inventory:manage_listings')


@login_required
@require_business
def view_enquiries(request: HttpRequest) -> HttpResponse:
    """
    View all enquiries for this business's listings.
    
    Permissions: Manager or Admin only
    """
    business = request.active_business
    
    # Get all enquiries for this business
    enquiries = (
        MarketplaceEnquiry.objects
        .filter(business=business)
        .select_related('listing')
        .order_by('-created_at')
    )
    
    # Paginate (20 per page)
    paginator = Paginator(enquiries, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/view_enquiries.html', {
        'page_obj': page_obj,
    })


@login_required
@require_business
@require_http_methods(['POST'])
def mark_enquiry_read(request: HttpRequest, enquiry_id: int) -> HttpResponse:
    """
    Mark an enquiry as read.
    
    Permissions: Manager or Admin only
    """
    business = request.active_business
    enquiry = get_object_or_404(MarketplaceEnquiry, id=enquiry_id, business=business)
    
    enquiry.mark_as_read()
    
    return JsonResponse({'ok': True})

