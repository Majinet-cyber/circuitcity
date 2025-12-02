# CircuitCity Wallet Enhancements - Integration Guide

## Quick Start Integration

This guide shows how to integrate the new wallet features into your existing dashboards.

---

## 1. Add Profit Panel to Any Dashboard

### Step 1: Import helpers in your view

```python
from dashboard.dashboard_metrics import add_profit_context, add_payment_mix_context, get_mtd_dates
from decimal import Decimal
from django.db.models import Sum
```

### Step 2: Calculate revenue (your existing logic)

```python
@login_required
def my_dashboard(request):
    business = request.business
    start_date, end_date = get_mtd_dates()
    
    # Your existing revenue calculation
    sales_qs = Sale.objects.filter(
        business=business,
        sold_at__gte=start_date,
        sold_at__lte=end_date
    )
    revenue = sales_qs.aggregate(total=Sum('price'))['total'] or Decimal("0.00")
    
    # Build your context as usual
    context = {
        'business': business,
        # ... other context vars
    }
    
    # ADD THIS: Profit metrics
    context = add_profit_context(context, business, revenue, start_date, end_date, "MTD")
    
    # ADD THIS: Payment mix
    context = add_payment_mix_context(context, sales_qs, "MTD")
    
    return render(request, 'my_dashboard.html', context)
```

### Step 3: Add to template

```html
{% extends "base.html" %}

{% block content %}
<div class="container-fluid py-4">
    <h2>My Dashboard</h2>
    
    <!-- ADD THIS: Profit Panel -->
    {% include "partials/profit_panel.html" %}
    
    <!-- ADD THIS: Payment Mix -->
    {% include "partials/payment_mix_panel.html" %}
    
    <!-- Your existing dashboard content -->
    ...
</div>
{% endblock %}
```

That's it! You now have Revenue/Costs/Profit and Payment Mix panels.

---

## 2. Wire Up Commission Tracking

### For Phones (sales/models.py):

```python
# Add this signal handler
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Sale)
def create_sale_commission(sender, instance, created, **kwargs):
    """Auto-create commission when sale is created."""
    if created and instance.agent:
        try:
            from wallet.agent_models import get_or_create_agent_wallet, add_commission
            from tenants.models import Membership
            
            # Find the agent's membership for this business
            membership = Membership.objects.filter(
                user=instance.agent,
                business=instance.location.business,
                role="AGENT",
                status="ACTIVE"
            ).first()
            
            if membership:
                # Calculate commission (use sale's commission_pct or business config)
                commission = instance.commission_amount  # Already calculated property
                
                # Add commission to agent wallet
                add_commission(
                    membership=membership,
                    amount=commission,
                    description=f"Sale commission: {instance.item.product.name}",
                    related_sale_id=instance.id,
                    related_sale_model="Sale",
                )
        except Exception as e:
            import logging
            logging.exception(f"Failed to create commission for sale {instance.id}: {e}")
```

### For Liquor (inventory/models_verticals.py):

```python
@receiver(post_save, sender=LiquorSale)
def create_liquor_commission(sender, instance, created, **kwargs):
    """Auto-create commission for liquor sales."""
    if created and instance.sold_by:
        try:
            from wallet.agent_models import add_commission
            from tenants.models import Membership
            
            membership = Membership.objects.filter(
                user=instance.sold_by,
                business=instance.business,
                role="AGENT",
                status="ACTIVE"
            ).first()
            
            if membership:
                # Calculate commission (e.g., 2% of profit)
                commission = instance.profit * Decimal("0.02")
                
                if commission > Decimal("0.00"):
                    add_commission(
                        membership=membership,
                        amount=commission,
                        description=f"Liquor sale commission: {instance.product.name}",
                        related_sale_id=instance.id,
                        related_sale_model="LiquorSale",
                    )
        except Exception as e:
            import logging
            logging.exception(f"Failed to create liquor commission: {e}")
```

### For Clothing (similar pattern):

```python
@receiver(post_save, sender=ClothingSale)
def create_clothing_commission(sender, instance, created, **kwargs):
    # Similar to above
    pass
```

---

## 3. Auto Deduct Penalties from TimeLog

### In timelogs/models.py or signals:

```python
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=AgentWorkLog)
def process_timelog_penalties(sender, instance, created, **kwargs):
    """
    Auto-deduct penalties from agent wallet when timelog is finalized.
    Only process once (wallet_processed=False).
    """
    if instance.wallet_processed:
        return  # Already processed
    
    # Only process if there's a penalty and the worklog is complete
    if instance.penalty_amount > Decimal("0.00") and instance.last_seen_at:
        try:
            from wallet.agent_models import add_deduction
            from tenants.models import Membership
            
            membership = Membership.objects.filter(
                user=instance.agent,
                business=instance.business,
                role="AGENT",
                status="ACTIVE"
            ).first()
            
            if membership:
                add_deduction(
                    membership=membership,
                    amount=instance.penalty_amount,
                    description=f"Lateness penalty: {instance.arrived_late_minutes} min late on {instance.work_date}",
                    related_timelog=instance,
                )
                
                # Mark as processed
                instance.wallet_processed = True
                instance.save(update_fields=['wallet_processed'])
                
        except Exception as e:
            import logging
            logging.exception(f"Failed to process timelog penalty: {e}")
```

---

## 4. Admin Manual Adjustments UI

### Already implemented! Just use it:

```python
from wallet.agent_models import add_manual_adjustment

# In your admin view:
@otp_required
def admin_adjust_agent_wallet(request, membership_id):
    membership = get_object_or_404(Membership, id=membership_id)
    
    if request.method == "POST":
        amount = Decimal(request.POST.get('amount'))
        is_debit = request.POST.get('is_debit') == 'true'
        reason = request.POST.get('reason')
        
        add_manual_adjustment(
            membership=membership,
            amount=amount,
            is_debit=is_debit,
            reason=reason,
            created_by=request.user,
        )
        
        messages.success(request, "Wallet adjusted successfully.")
        return redirect('agent_detail', membership_id=membership_id)
    
    return render(request, 'admin_adjust_wallet.html', {'membership': membership})
```

---

## 5. Agent Rankings on Dashboard

### In your agent dashboard view:

```python
from wallet.agent_models import get_agent_ranking, AgentEarnings

@login_required
def agent_dashboard(request):
    membership = request.user.memberships.filter(
        business=request.business,
        role="AGENT",
        status="ACTIVE"
    ).first()
    
    if not membership:
        return redirect('home')
    
    # Get earnings summary
    earnings = AgentEarnings(membership)
    
    # Get ranking
    ranking = get_agent_ranking(membership)
    
    context = {
        'membership': membership,
        'balance': earnings.balance,
        'mtd_earnings': earnings.mtd_earnings(),
        'mtd_deductions': earnings.mtd_deductions(),
        'mtd_net': earnings.mtd_net(),
        'lifetime_earnings': earnings.lifetime_earnings(),
        'ranking': ranking,
    }
    
    return render(request, 'agent_dashboard.html', context)
```

### In template:

```html
<!-- Agent Earnings Card -->
<div class="card mb-3">
    <div class="card-body">
        <h5>Your Wallet</h5>
        <h3>MK {{ balance|floatformat:0|intcomma }}</h3>
        <small class="text-muted">
            MTD Earnings: MK {{ mtd_earnings|floatformat:0|intcomma }} |
            MTD Deductions: MK {{ mtd_deductions|floatformat:0|intcomma }} |
            MTD Net: MK {{ mtd_net|floatformat:0|intcomma }}
        </small>
    </div>
</div>

<!-- Ranking Card -->
{% if ranking %}
<div class="card mb-3 border-warning">
    <div class="card-body">
        <h5><i class="bi bi-trophy"></i> Your Ranking</h5>
        <p class="mb-1">
            <strong>You are #{{ ranking.rank }}</strong> out of {{ ranking.total_agents }} agents this month.
        </p>
        {% if ranking.behind_top > 0 %}
        <p class="text-muted mb-0">
            Only {{ ranking.behind_top }} sales behind #1. Keep going!
        </p>
        {% elif ranking.is_top %}
        <p class="text-success mb-0">
            <strong>You're #1! Great work!</strong>
        </p>
        {% endif %}
    </div>
</div>
{% endif %}
```

---

## 6. Enhanced Signup with Email Validation

### In tenants/views.py (or your signup view):

```python
from django.contrib.auth import get_user_model

User = get_user_model()

def signup(request):
    if request.method == "POST":
        email = request.POST.get('email', '').strip().lower()
        
        # Check if email exists
        if User.objects.filter(email__iexact=email).exists():
            messages.error(
                request,
                "This email is already registered. Please log in instead or use a different email."
            )
            return render(request, 'signup.html', {'form': form})
        
        # Password validation
        password = request.POST.get('password', '')
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, 'signup.html', {'form': form})
        
        # Continue with user creation...
```

---

## 7. Run Migrations

```bash
# Apply all new migrations
python manage.py migrate sales
python manage.py migrate inventory
python manage.py migrate timelogs
python manage.py migrate wallet
```

---

## 8. Test the Features

### Create a test cost:

```python
python manage.py shell

from wallet.models import WalletTransaction, Ledger, TxnType
from tenants.models import Business
from decimal import Decimal

biz = Business.objects.first()

# Create once-off cost
WalletTransaction.objects.create(
    ledger=Ledger.COMPANY,
    type=TxnType.COST_ONCE_OFF,
    amount=Decimal("-50000.00"),  # Negative for expense
    note="Office supplies",
    business=biz,
)

# Create recurring cost
WalletTransaction.objects.create(
    ledger=Ledger.COMPANY,
    type=TxnType.COST_RECURRING,
    amount=Decimal("-200000.00"),  # Rent
    note="Monthly office rent",
    is_recurring=True,
    recurrence="monthly",
    effective_from=date(2025, 1, 1),
    business=biz,
)
```

### Check profit calculation:

```python
from wallet.utils import compute_revenue_costs_profit
from decimal import Decimal
from datetime import date

# Assuming you have revenue of 1,000,000 for January
result = compute_revenue_costs_profit(
    business=biz,
    revenue=Decimal("1000000.00"),
    start_date=date(2025, 1, 1),
    end_date=date(2025, 1, 31),
)

print(f"Revenue: {result['revenue']}")
print(f"Costs: {result['costs']}")
print(f"Profit: {result['profit']}")
print(f"Profit Margin: {result['profit_margin']}%")
```

---

## 9. Admin Access

### Access cost management:

```
/wallet/admin/costs/
```

This shows all costs and lets you add/edit/delete them.

---

## 10. Troubleshooting

### If profit panel doesn't show:

1. Check that `wallet.utils` is importable
2. Verify business has cost transactions
3. Check template includes are correct
4. Look at Django logs for exceptions

### If commissions don't work:

1. Verify agent has active membership
2. Check signal is registered (add to `apps.py` ready method)
3. Verify commission calculation logic
4. Check wallet transaction logs

### If payments mix is empty:

1. Verify sales have `payment_method` field populated
2. Run migration if field doesn't exist
3. Check query is filtering correctly

---

## Summary

With these integrations, you now have:

✅ Revenue/Costs/Profit panels on all dashboards
✅ Payment mix breakdown (Cash/Bank/Mobile Money)
✅ Auto-commission on sales
✅ Auto-penalties from timelogs
✅ Admin cost management UI
✅ Agent rankings and earnings tracking
✅ Enhanced signup validation

All features are backward-compatible and won't break existing functionality!

---

## Next Steps

1. Integrate profit panels into each vertical dashboard
2. Add signal handlers for commission tracking
3. Test with real data
4. Write additional tests for edge cases
5. Update documentation for your team

---

For questions or issues, refer to:
- `WALLET_ENHANCEMENTS_IMPLEMENTATION.md` - Full implementation details
- `wallet/agent_models.py` - Agent wallet API reference
- `dashboard/dashboard_metrics.py` - Dashboard helpers

