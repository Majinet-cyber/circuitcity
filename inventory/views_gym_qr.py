# inventory/views_gym_qr.py
"""
Gym QR code scanner views for member check-in.
"""
from __future__ import annotations

from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST, require_GET

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models_verticals import GymMember, GymCheckIn
from tenants.utils import require_business


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@require_http_methods(["GET"])
def qr_scanner(request):
    """
    QR code scanner page for gym member check-in.
    Opens rear camera and scans QR codes.
    """
    business = get_active_business(request)
    
    context = {
        "business": business,
    }
    
    return render(request, "verticals/gym/qr_scanner.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@require_POST
def qr_lookup(request):
    """
    API endpoint to lookup member by QR token and return member info.
    Returns JSON with member details and membership status.
    """
    business = get_active_business(request)
    qr_token = request.POST.get("qr_token", "").strip()
    
    if not qr_token:
        return JsonResponse({
            "success": False,
            "error": "QR code is required"
        }, status=400)
    
    try:
        member = GymMember.objects.get(
            business=business,
            qr_token=qr_token,
            is_active=True,
            is_archived=False
        )
    except GymMember.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Member not found. Check QR code."
        }, status=404)
    
    # Get membership status
    today = date.today()
    is_expired = False
    days_left = 0
    expiry_date = None
    
    if member.membership_end:
        expiry_date = member.membership_end.isoformat()
        days_left = (member.membership_end - today).days
        is_expired = member.membership_end < today
    else:
        is_expired = True  # No membership period set
    
    # Determine status text
    if is_expired:
        status_text = "Expired"
        status_class = "expired"
    elif days_left <= 3:
        status_text = "Expires Soon"
        status_class = "warning"
    else:
        status_text = "Active"
        status_class = "active"
    
    # Log check-in
    try:
        GymCheckIn.objects.create(
            business=business,
            member=member,
            checked_in_at=timezone.now(),
            checked_in_by=request.user
        )
    except Exception:
        pass  # Don't fail if check-in logging fails
    
    return JsonResponse({
        "success": True,
        "member": {
            "id": member.id,
            "name": member.name,
            "phone": member.phone,
            "email": member.email or "",
            "trainer": member.trainer.name if member.trainer else None,
            "status": status_text,
            "status_class": status_class,
            "is_expired": is_expired,
            "days_left": days_left if not is_expired else 0,
            "expiry_date": expiry_date,
            "membership_start": member.membership_start.isoformat() if member.membership_start else None,
        }
    })


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@require_http_methods(["GET"])
def qr_scan_result(request, member_id: int):
    """
    Display member information after QR scan (dedicated page).
    Shows status, days remaining/arrears, and member details.
    """
    business = get_active_business(request)
    member = get_object_or_404(
        GymMember,
        id=member_id,
        business=business,
        is_active=True,
        is_archived=False
    )
    
    # Get membership status
    today = date.today()
    is_expired = False
    days_left = 0
    arrears_days = 0
    expiry_date = None
    
    if member.membership_end:
        expiry_date = member.membership_end
        days_left = (member.membership_end - today).days
        is_expired = member.membership_end < today
        if is_expired:
            arrears_days = (today - member.membership_end).days
    else:
        is_expired = True  # No membership period set
    
    # Determine status text
    if is_expired:
        status_text = "Expired"
        status_class = "expired"
    elif days_left <= 3:
        status_text = "Expires Soon"
        status_class = "warning"
    else:
        status_text = "Active"
        status_class = "active"
    
    # Log check-in
    try:
        GymCheckIn.objects.create(
            business=business,
            member=member,
            checked_in_at=timezone.now(),
            checked_in_by=request.user
        )
    except Exception:
        pass  # Don't fail if check-in logging fails
    
    context = {
        "member": member,
        "business": business,
        "status": status_text,
        "status_class": status_class,
        "is_expired": is_expired,
        "days_left": days_left,
        "arrears_days": arrears_days,
        "expiry_date": expiry_date,
    }
    
    return render(request, "verticals/gym/qr_scan_result.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@require_http_methods(["GET"])
def member_qr_card(request, member_id: int):
    """
    Display member's QR code card for printing/showing.
    """
    business = get_active_business(request)
    member = get_object_or_404(
        GymMember,
        id=member_id,
        business=business
    )
    
    # Get color theme for this member
    from inventory.utils_gym_qr import get_member_color_theme
    theme_color, theme_color_secondary, _ = get_member_color_theme(member.id, member.qr_token)
    
    context = {
        "member": member,
        "business": business,
        "theme_color": theme_color,
        "theme_color_secondary": theme_color_secondary,
    }
    
    return render(request, "verticals/gym/member_qr_card.html", context)


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@require_GET
def member_qr_card_download(request, member_id: int):
    """
    Download member's QR card as image or PDF.
    """
    business = get_active_business(request)
    member = get_object_or_404(
        GymMember,
        id=member_id,
        business=business
    )
    
    format_type = request.GET.get("format", "image").lower()
    
    try:
        from inventory.utils_gym_qr import generate_member_card_image, generate_member_card_pdf
        
        expiry_date_str = member.membership_end.strftime("%Y-%m-%d") if member.membership_end else None
        
        if format_type == "pdf":
            # Generate PDF
            pdf_bytes = generate_member_card_pdf(
                member_name=member.name,
                member_phone=member.phone,
                qr_token=member.qr_token,
                member_id=member.id,
                business_name=business.name,
                expiry_date=expiry_date_str,
            )
            
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="membership_card_{member.id}.pdf"'
            return response
        else:
            # Generate image (PNG)
            img_bytes = generate_member_card_image(
                member_name=member.name,
                member_phone=member.phone,
                qr_token=member.qr_token,
                member_id=member.id,
                business_name=business.name,
                expiry_date=expiry_date_str,
            )
            
            response = HttpResponse(img_bytes, content_type='image/png')
            response['Content-Disposition'] = f'attachment; filename="membership_card_{member.id}.png"'
            return response
    
    except ImportError as e:
        messages.error(request, f"Card generation not available: {str(e)}")
        return redirect("gym:member_detail", member_id=member.id)
    except Exception as e:
        messages.error(request, f"Error generating card: {str(e)}")
        return redirect("gym:member_detail", member_id=member.id)

