# inventory/views_gym.py
"""
Views for gym operations: member management, payments, 30-day memberships.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from inventory.authz import require_business_kind, manager_required
from inventory.business_kinds import BusinessKind
from inventory.helpers import get_active_business
from inventory.models_verticals import (
    GymMember, GymPayment, GymMemberLog, GymSettings, GymWalletEntry,
    GymMemberAction
)
from tenants.utils import require_business


# ==============================================================================
# GYM MEMBER CRUD
# ==============================================================================

class GymMemberForm(forms.ModelForm):
    """Form for adding/editing gym members"""
    class Meta:
        model = GymMember
        fields = ["name", "phone", "email", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Member name"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone number"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email (optional)"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Additional notes (optional)"}),
        }


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def members_list(request):
    """List all gym members"""
    business = get_active_business(request)
    
    # Filter: active, archived, or all
    filter_type = request.GET.get("filter", "active")
    members = GymMember.objects.filter(business=business)
    
    if filter_type == "active":
        members = members.filter(is_active=True, is_archived=False)
    elif filter_type == "archived":
        members = members.filter(is_archived=True)
    # else: show all
    
    members = members.order_by("-joined_at")
    
    return render(request, "inventory/gym/members_list.html", {
        "members": members,
        "business": business,
        "filter_type": filter_type,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def member_add(request):
    """Add a new gym member"""
    business = get_active_business(request)
    
    if request.method == "POST":
        form = GymMemberForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                member = form.save(commit=False)
                member.business = business
                member.save()
                
                # Log the creation
                GymMemberLog.objects.create(
                    member=member,
                    action=GymMemberAction.CREATED,
                    changes={"name": member.name, "phone": member.phone, "email": member.email},
                    performed_by=request.user
                )
            
            messages.success(request, f"Member '{member.name}' added successfully.")
            return redirect("inventory:gym_member_detail", member_id=member.id)
    else:
        form = GymMemberForm()
    
    return render(request, "inventory/gym/member_form.html", {
        "form": form,
        "business": business,
        "title": "Add New Member",
    })


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def member_edit(request, member_id):
    """Edit an existing gym member"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)
    
    if request.method == "POST":
        form = GymMemberForm(request.POST, instance=member)
        if form.is_valid():
            # Track what changed
            changes = {}
            for field in ["name", "phone", "email", "notes"]:
                old_val = getattr(member, field)
                new_val = form.cleaned_data.get(field)
                if old_val != new_val:
                    changes[field] = {"old": old_val, "new": new_val}
            
            with transaction.atomic():
                member = form.save()
                
                # Log the update
                if changes:
                    GymMemberLog.objects.create(
                        member=member,
                        action=GymMemberAction.UPDATED,
                        changes=changes,
                        performed_by=request.user
                    )
            
            messages.success(request, f"Member '{member.name}' updated successfully.")
            return redirect("inventory:gym_member_detail", member_id=member.id)
    else:
        form = GymMemberForm(instance=member)
    
    return render(request, "inventory/gym/member_form.html", {
        "form": form,
        "member": member,
        "business": business,
        "title": "Edit Member",
    })


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def member_detail(request, member_id):
    """View member details with payment history and logs"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)
    
    # Get payment history
    payments = member.payments.select_related("paid_by").order_by("-paid_at")
    
    # Get logs
    logs = member.logs.select_related("performed_by").order_by("-created_at")
    
    # Get gym settings for contact info
    try:
        gym_settings = GymSettings.objects.get(business=business)
    except GymSettings.DoesNotExist:
        gym_settings = None
    
    # Calculate membership status
    days_left = member.days_left()
    status = member.membership_status()
    
    return render(request, "inventory/gym/member_detail.html", {
        "member": member,
        "payments": payments,
        "logs": logs,
        "days_left": days_left,
        "status": status,
        "gym_settings": gym_settings,
        "business": business,
    })


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
@require_POST
def member_archive(request, member_id):
    """Archive a gym member"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)
    
    with transaction.atomic():
        member.archive(request.user)
        
        # Log the archival
        GymMemberLog.objects.create(
            member=member,
            action=GymMemberAction.ARCHIVED,
            changes={"archived_at": str(timezone.now())},
            performed_by=request.user
        )
    
    messages.success(request, f"Member '{member.name}' archived.")
    return redirect("inventory:gym_members_list")


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
@require_POST
def member_restore(request, member_id):
    """Restore an archived member"""
    business = get_active_business(request)
    member = get_object_or_404(GymMember, pk=member_id, business=business)
    
    with transaction.atomic():
        member.is_archived = False
        member.is_active = True
        member.archived_at = None
        member.archived_by = None
        member.save(update_fields=["is_archived", "is_active", "archived_at", "archived_by"])
        
        # Log the restoration
        GymMemberLog.objects.create(
            member=member,
            action=GymMemberAction.RESTORED,
            changes={"restored_at": str(timezone.now())},
            performed_by=request.user
        )
    
    messages.success(request, f"Member '{member.name}' restored.")
    return redirect("inventory:gym_member_detail", member_id=member.id)


# ==============================================================================
# GYM PAYMENTS (30-day memberships)
# ==============================================================================

class GymPaymentForm(forms.Form):
    """Form for recording a gym membership payment"""
    member = forms.ModelChoiceField(
        queryset=GymMember.objects.none(),
        widget=forms.Select(attrs={"class": "form-control"})
    )
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"})
    )
    start_date = forms.DateField(
        initial=date.today,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional notes"})
    )
    
    def __init__(self, business=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if business:
            self.fields["member"].queryset = GymMember.objects.filter(
                business=business,
                is_active=True,
                is_archived=False
            ).order_by("name")


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def add_payment(request):
    """Record a new gym membership payment (30 days)"""
    business = get_active_business(request)
    
    # Get default price from settings
    try:
        gym_settings = GymSettings.objects.get(business=business)
        default_price = gym_settings.default_membership_price
    except GymSettings.DoesNotExist:
        default_price = Decimal("50000.00")
    
    if request.method == "POST":
        form = GymPaymentForm(business, request.POST)
        if form.is_valid():
            data = form.cleaned_data
            
            with transaction.atomic():
                # Determine start date: either today or end of previous membership
                member = data["member"]
                latest_payment = member.payments.filter(is_active=True).order_by("-end_date").first()
                
                if latest_payment and latest_payment.end_date >= data["start_date"]:
                    # Extend from previous end date
                    start_date = latest_payment.end_date + timedelta(days=1)
                else:
                    # Start from specified date
                    start_date = data["start_date"]
                
                # Always 30 days
                end_date = start_date + timedelta(days=30)
                
                # Create payment
                payment = GymPayment.objects.create(
                    member=member,
                    amount=data["amount"],
                    start_date=start_date,
                    end_date=end_date,
                    paid_by=request.user,
                    notes=data.get("notes", "")
                )
                
                # Create wallet entry
                GymWalletEntry.objects.create(
                    business=business,
                    amount=data["amount"],
                    description=f"Membership payment from {member.name}",
                    entry_type="income",
                    related_payment=payment,
                    created_by=request.user
                )
            
            messages.success(request, f"Payment recorded. Membership valid until {end_date.strftime('%Y-%m-%d')}.")
            return redirect("inventory:gym_member_detail", member_id=member.id)
    else:
        form = GymPaymentForm(business, initial={"amount": default_price})
    
    recent_payments = GymPayment.objects.filter(member__business=business).select_related("member", "paid_by").order_by("-paid_at")[:10]
    
    return render(request, "inventory/gym/payment_form.html", {
        "form": form,
        "recent_payments": recent_payments,
        "business": business,
    })


# ==============================================================================
# GYM DASHBOARD
# ==============================================================================

@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
def gym_dashboard(request):
    """Gym business dashboard with member stats and arrears"""
    business = get_active_business(request)
    
    # Get active members
    active_members = GymMember.objects.filter(business=business, is_active=True, is_archived=False)
    
    # Calculate members in arrears
    members_in_arrears = []
    members_active_count = 0
    
    for member in active_members:
        days_left = member.days_left()
        if days_left == 0:
            members_in_arrears.append(member)
        else:
            members_active_count += 1
    
    # Recent payments
    recent_payments = GymPayment.objects.filter(member__business=business).select_related("member", "paid_by").order_by("-paid_at")[:10]
    
    # Get gym settings
    try:
        gym_settings = GymSettings.objects.get(business=business)
    except GymSettings.DoesNotExist:
        gym_settings = None
    
    return render(request, "inventory/gym/dashboard.html", {
        "business": business,
        "total_members": active_members.count(),
        "members_active_count": members_active_count,
        "members_in_arrears_count": len(members_in_arrears),
        "members_in_arrears": members_in_arrears,
        "recent_payments": recent_payments,
        "gym_settings": gym_settings,
    })


# ==============================================================================
# GYM SETTINGS
# ==============================================================================

class GymSettingsForm(forms.ModelForm):
    """Form for gym business settings"""
    class Meta:
        model = GymSettings
        fields = ["support_phone", "support_email", "default_membership_price", "arrears_message"]
        widgets = {
            "support_phone": forms.TextInput(attrs={"class": "form-control"}),
            "support_email": forms.EmailInput(attrs={"class": "form-control"}),
            "default_membership_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "arrears_message": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


@login_required
@require_business
@require_business_kind(BusinessKind.GYM)
@manager_required
def gym_settings_view(request):
    """Manage gym settings"""
    business = get_active_business(request)
    
    # Get or create settings
    gym_settings, created = GymSettings.objects.get_or_create(business=business)
    
    if request.method == "POST":
        form = GymSettingsForm(request.POST, instance=gym_settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Gym settings updated.")
            return redirect("inventory:gym_dashboard")
    else:
        form = GymSettingsForm(instance=gym_settings)
    
    return render(request, "inventory/gym/settings.html", {
        "form": form,
        "gym_settings": gym_settings,
        "business": business,
    })

