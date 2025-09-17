# tenants/views_join.py
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils.text import slugify

from .models import Business, Membership

# Billing: seed a trial on creation
try:
    from billing.models import SubscriptionPlan, BusinessSubscription  # new billing models
except Exception:  # pragma: no cover
    SubscriptionPlan = None  # type: ignore
    BusinessSubscription = None  # type: ignore


# --- Form ---
class CreateBusinessForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        label="Business name",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Acme Stores"})
    )
    slug = forms.SlugField(
        max_length=80,
        required=False,
        help_text="Used in URL as /t/<slug>/. Leave blank to auto-generate.",
        widget=forms.TextInput(attrs={"placeholder": "acme-stores"})
    )

    def clean(self):
        data = super().clean()
        name = (data.get("name") or "").strip()
        slug = (data.get("slug") or "").strip()

        if not name:
            self.add_error("name", "Please enter a business name.")

        # Auto-generate slug if blank
        if not slug and name:
            slug = slugify(name)
            data["slug"] = slug

        if slug:
            exists = Business.objects.filter(slug__iexact=slug).exists()
            if exists:
                self.add_error("slug", "That slug is already taken. Please choose another.")

        return data


# --- View: self-serve manager creation ---
@login_required
def join(request):
    """
    Self-serve path for managers to create a Business and start a trial immediately.

    Flow:
      - Create Business(status='ACTIVE')
      - Create Membership(user=creator, role='MANAGER', status='ACTIVE')
      - Seed trial subscription on the cheapest active plan (if billing is present)
      - Set session['active_business_id'] and redirect to /t/<slug>/
    """
    if request.method == "POST":
        form = CreateBusinessForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"].strip()
            slug = form.cleaned_data["slug"].strip() or slugify(name)

            # Create ACTIVE business (no staff approval for self-serve)
            biz = Business.objects.create(
                name=name,
                slug=slug,
                status="ACTIVE",
                created_by=request.user if hasattr(Business, "created_by") else None,
            )

            # Creator becomes MANAGER (ACTIVE)
            Membership.objects.create(
                user=request.user,
                business=biz,
                role="MANAGER",
                status="ACTIVE",
            )

            # Seed a trial subscription (best-effort)
            if SubscriptionPlan and BusinessSubscription:
                plan = SubscriptionPlan.objects.filter(is_active=True).order_by("amount").first()
                if not plan:
                    # ensure there is at least a starter plan
                    plan = SubscriptionPlan.objects.create(
                        code="starter",
                        name="Starter",
                        amount=0,
                        is_active=True,
                    )
                BusinessSubscription.start_trial(business=biz, plan=plan)

            # Switch context for this session
            request.session["active_business_id"] = str(biz.id)

            messages.success(request, f"{name} created. You’re now managing this business.")
            return redirect(f"/t/{slug}/")
    else:
        form = CreateBusinessForm()

    return render(request, "tenants/join.html", {"form": form})
