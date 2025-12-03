# inventory/views_phone_sale_wizard.py
"""
Gamified Phone Sale Wizard

A fun, guided multi-step flow for recording phone sales:
1. Brand selection (big cards with brand logos)
2. Model selection (from catalog)
3. RAM/ROM variant selection
4. IMEI capture (with validation)
5. Price & confirmation

Makes selling phones feel like a game, not a chore!
"""
from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from tenants.utils import require_business
from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models import InventoryItem, Location
from inventory.models_phone_products import PhoneProductCatalog
from inventory.phone_catalog_seed import get_brands_for_business, get_models_for_brand
from inventory.verticals import base


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
def phone_sale_wizard(request):
    """
    Gamified phone sale wizard - multi-step flow.
    
    Steps:
    1. Brand selection
    2. Model selection (filtered by brand)
    3. Variant selection (RAM/ROM)
    4. IMEI capture
    5. Price & confirmation
    
    Uses session to track progress through steps.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    # Get current step from session (default to step 1)
    step = int(request.GET.get("step", request.session.get("sale_wizard_step", 1)))
    
    # Check if we're coming from a product link (skip to step 4 - IMEI)
    product_id = request.GET.get("product_id")
    if product_id:
        try:
            product = PhoneProductCatalog.objects.get(id=product_id, business=business)
            # Pre-fill wizard data
            request.session["sale_wizard_brand"] = product.brand
            request.session["sale_wizard_model"] = product.model_name
            request.session["sale_wizard_variant"] = product.variant_label
            request.session["sale_wizard_product_id"] = product.id
            step = 4  # Jump to IMEI entry
        except PhoneProductCatalog.DoesNotExist:
            messages.error(request, "Product not found")
            return redirect("inventory:phone_products")
    
    # Store step in session
    request.session["sale_wizard_step"] = step
    
    # Route to appropriate step handler
    if step == 1:
        return _wizard_step_brand(request, ctx, business)
    elif step == 2:
        return _wizard_step_model(request, ctx, business)
    elif step == 3:
        return _wizard_step_variant(request, ctx, business)
    elif step == 4:
        return _wizard_step_imei(request, ctx, business)
    elif step == 5:
        return _wizard_step_confirm(request, ctx, business)
    else:
        # Reset wizard
        _clear_wizard_session(request)
        return redirect("inventory:phone_sale_wizard")


def _clear_wizard_session(request):
    """Clear wizard session data"""
    keys_to_clear = [
        "sale_wizard_step",
        "sale_wizard_brand",
        "sale_wizard_model",
        "sale_wizard_variant",
        "sale_wizard_product_id",
        "sale_wizard_imei",
        "sale_wizard_selling_price",
    ]
    for key in keys_to_clear:
        request.session.pop(key, None)


def _wizard_step_brand(request, ctx, business):
    """Step 1: Brand selection"""
    if request.method == "POST":
        brand = request.POST.get("brand", "").strip().upper()
        if brand:
            request.session["sale_wizard_brand"] = brand
            request.session["sale_wizard_step"] = 2
            return redirect("inventory:phone_sale_wizard?step=2")
        else:
            messages.error(request, "Please select a brand")
    
    # Get available brands
    brands = get_brands_for_business(business)
    
    ctx.update({
        "step": 1,
        "step_title": "Step 1: Choose Brand",
        "step_description": "Select the phone brand you're selling",
        "brands": brands,
        "progress_pct": 20,
    })
    
    return render(request, "verticals/phones/sale_wizard.html", ctx)


def _wizard_step_model(request, ctx, business):
    """Step 2: Model selection"""
    brand = request.session.get("sale_wizard_brand")
    if not brand:
        return redirect("inventory:phone_sale_wizard?step=1")
    
    if request.method == "POST":
        model = request.POST.get("model", "").strip()
        product_id = request.POST.get("product_id", "").strip()
        if model and product_id:
            request.session["sale_wizard_model"] = model
            request.session["sale_wizard_product_id"] = product_id
            request.session["sale_wizard_step"] = 3
            return redirect("inventory:phone_sale_wizard?step=3")
        else:
            messages.error(request, "Please select a model")
    
    # Get models for selected brand
    models = get_models_for_brand(business, brand)
    
    # Group by model_name for display
    models_grouped = {}
    for model in models:
        model_name = model["model_name"]
        if model_name not in models_grouped:
            models_grouped[model_name] = []
        models_grouped[model_name].append(model)
    
    ctx.update({
        "step": 2,
        "step_title": f"Step 2: Choose {brand} Model",
        "step_description": "Select the specific model",
        "brand": brand,
        "models_grouped": models_grouped,
        "progress_pct": 40,
    })
    
    return render(request, "verticals/phones/sale_wizard.html", ctx)


def _wizard_step_variant(request, ctx, business):
    """Step 3: Variant (RAM/ROM) selection"""
    brand = request.session.get("sale_wizard_brand")
    model = request.session.get("sale_wizard_model")
    if not brand or not model:
        return redirect("inventory:phone_sale_wizard?step=1")
    
    if request.method == "POST":
        variant = request.POST.get("variant", "").strip()
        product_id = request.POST.get("product_id", "").strip()
        if variant and product_id:
            request.session["sale_wizard_variant"] = variant
            request.session["sale_wizard_product_id"] = product_id
            request.session["sale_wizard_step"] = 4
            return redirect("inventory:phone_sale_wizard?step=4")
        else:
            messages.error(request, "Please select a variant")
    
    # Get variants for selected model
    product_id = request.session.get("sale_wizard_product_id")
    if product_id:
        # If we already have a product_id (from step 2), get its variants
        try:
            product = PhoneProductCatalog.objects.get(id=product_id, business=business)
            models = get_models_for_brand(business, brand)
            variants = [m for m in models if m["model_name"] == model]
        except PhoneProductCatalog.DoesNotExist:
            return redirect("inventory:phone_sale_wizard?step=1")
    else:
        models = get_models_for_brand(business, brand)
        variants = [m for m in models if m["model_name"] == model]
    
    ctx.update({
        "step": 3,
        "step_title": f"Step 3: Choose {brand} {model} Variant",
        "step_description": "Select RAM and Storage configuration",
        "brand": brand,
        "model": model,
        "variants": variants,
        "progress_pct": 60,
    })
    
    return render(request, "verticals/phones/sale_wizard.html", ctx)


def _wizard_step_imei(request, ctx, business):
    """Step 4: IMEI capture"""
    brand = request.session.get("sale_wizard_brand")
    model = request.session.get("sale_wizard_model")
    variant = request.session.get("sale_wizard_variant")
    product_id = request.session.get("sale_wizard_product_id")
    
    if not all([brand, model, variant, product_id]):
        return redirect("inventory:phone_sale_wizard?step=1")
    
    if request.method == "POST":
        imei = request.POST.get("imei", "").strip()
        
        # Validate IMEI
        if not imei:
            messages.error(request, "IMEI is required")
        elif len(imei) != 15 or not imei.isdigit():
            messages.error(request, "IMEI must be exactly 15 digits")
        else:
            # Check for duplicates (active stock with same IMEI)
            existing = InventoryItem.objects.filter(
                business=business,
                imei=imei,
                status="IN_STOCK",
                is_active=True
            ).first()
            
            if existing:
                messages.error(
                    request,
                    f"IMEI {imei} already exists in stock (ID: {existing.id}). Cannot add duplicate."
                )
            else:
                request.session["sale_wizard_imei"] = imei
                request.session["sale_wizard_step"] = 5
                return redirect("inventory:phone_sale_wizard?step=5")
    
    # Get product details for display
    try:
        product = PhoneProductCatalog.objects.get(id=product_id, business=business)
    except PhoneProductCatalog.DoesNotExist:
        return redirect("inventory:phone_sale_wizard?step=1")
    
    # Fun motivational messages
    motivational_messages = [
        f"Nice choice! {brand} {model} is a bestseller. 📱",
        f"You're doing great! Just need the IMEI now. 🚀",
        f"Almost there! IMEI is the final piece. 💪",
    ]
    import random
    motivational_msg = random.choice(motivational_messages)
    
    ctx.update({
        "step": 4,
        "step_title": "Step 4: Enter IMEI",
        "step_description": "Scan or type the 15-digit IMEI number",
        "brand": brand,
        "model": model,
        "variant": variant,
        "product": product,
        "motivational_msg": motivational_msg,
        "progress_pct": 80,
    })
    
    return render(request, "verticals/phones/sale_wizard.html", ctx)


def _wizard_step_confirm(request, ctx, business):
    """Step 5: Price & confirmation"""
    brand = request.session.get("sale_wizard_brand")
    model = request.session.get("sale_wizard_model")
    variant = request.session.get("sale_wizard_variant")
    product_id = request.session.get("sale_wizard_product_id")
    imei = request.session.get("sale_wizard_imei")
    
    if not all([brand, model, variant, product_id, imei]):
        return redirect("inventory:phone_sale_wizard?step=1")
    
    # Get product details
    try:
        catalog_product = PhoneProductCatalog.objects.get(id=product_id, business=business)
    except PhoneProductCatalog.DoesNotExist:
        return redirect("inventory:phone_sale_wizard?step=1")
    
    if request.method == "POST":
        selling_price = request.POST.get("selling_price", "").strip()
        cost_price = request.POST.get("cost_price", "").strip()
        
        # Validation
        try:
            selling_price = Decimal(selling_price) if selling_price else Decimal("0.00")
            cost_price = Decimal(cost_price) if cost_price else Decimal("0.00")
        except Exception:
            messages.error(request, "Invalid price format")
            return redirect("inventory:phone_sale_wizard?step=5")
        
        if selling_price <= 0:
            messages.error(request, "Selling price must be greater than zero")
            return redirect("inventory:phone_sale_wizard?step=5")
        
        # Create the inventory item (SOLD status)
        location = ctx.get("location") or Location.default_for(business)
        if not location:
            messages.error(request, "No location found. Please set up a location first.")
            return redirect("inventory:phone_sale_wizard?step=5")
        
        # Find or create Product (global SKU)
        from inventory.models import Product
        product, _ = Product.objects.get_or_create(
            brand=brand,
            model=model,
            variant=variant,
            defaults={
                "code": f"{brand}_{model}_{variant}".replace(" ", "_").upper(),
                "name": f"{brand} {model} {variant}",
                "cost_price": cost_price,
                "sale_price": selling_price,
            }
        )
        
        # Create inventory item as SOLD
        item = InventoryItem.objects.create(
            business=business,
            imei=imei,
            product=product,
            order_price=cost_price,
            selling_price=selling_price,
            status="SOLD",
            current_location=location,
            assigned_agent=request.user,
            sold_at=timezone.now(),
        )
        
        # Clear wizard session
        _clear_wizard_session(request)
        
        messages.success(
            request,
            f"🎉 Sale recorded! {brand} {model} {variant} (IMEI: {imei}) sold for MK {selling_price:,.0f}"
        )
        
        # Check if user is close to top agent
        try:
            from inventory.services.agent_ranking import compute_agent_ranking
            ranking = compute_agent_ranking(business, period_days=30)
            user_rank = next((r for r in ranking if r["agent_id"] == request.user.id), None)
            if user_rank and user_rank["rank"] <= 5:
                messages.info(
                    request,
                    f"🏆 You're #{user_rank['rank']} in sales this month! Keep it up!"
                )
        except Exception:
            pass
        
        return redirect("inventory:inventory_dashboard")
    
    # Pre-fill prices from catalog if available
    default_selling_price = catalog_product.default_selling_price or Decimal("0.00")
    default_cost_price = catalog_product.default_cost_price or Decimal("0.00")
    
    ctx.update({
        "step": 5,
        "step_title": "Step 5: Confirm Sale",
        "step_description": "Review details and set final price",
        "brand": brand,
        "model": model,
        "variant": variant,
        "imei": imei,
        "catalog_product": catalog_product,
        "default_selling_price": default_selling_price,
        "default_cost_price": default_cost_price,
        "progress_pct": 100,
    })
    
    return render(request, "verticals/phones/sale_wizard.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.PHONES)
@require_http_methods(["POST"])
def phone_sale_wizard_reset(request):
    """Reset the wizard and start over"""
    _clear_wizard_session(request)
    messages.info(request, "Wizard reset. Starting fresh!")
    return redirect("inventory:phone_sale_wizard")

