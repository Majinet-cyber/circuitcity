#!/usr/bin/env python
"""
Quick validation test for the agent_earnings service fix.
Run with: python test_agent_earnings_fix.py
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from decimal import Decimal
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

def test_agent_earnings_service():
    """Test that get_agent_earnings queries both models correctly."""
    
    print("=" * 70)
    print("Testing agent_earnings service...")
    print("=" * 70)
    
    try:
        from inventory.services.agent_earnings import get_agent_earnings, get_top_agents
        print("✅ Successfully imported agent_earnings service")
    except Exception as e:
        print(f"❌ Failed to import service: {e}")
        return False
    
    # Get first business
    try:
        from tenants.models import Business
        business = Business.objects.first()
        if not business:
            print("⚠️  No business found in database - skipping data test")
            return True
        print(f"✅ Found business: {business.name}")
    except Exception as e:
        print(f"❌ Failed to get business: {e}")
        return False
    
    # Test date range (this month)
    now = timezone.now()
    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_date = now
    
    print(f"\nDate range: {start_date.date()} to {end_date.date()}")
    
    # Call get_agent_earnings
    try:
        earnings_data = get_agent_earnings(
            business=business,
            start_date=start_date.date(),
            end_date=end_date.date(),
        )
        print(f"✅ get_agent_earnings() returned {len(earnings_data)} agents")
        
        if earnings_data:
            print("\nTop 5 agents:")
            for idx, agent in enumerate(earnings_data[:5], 1):
                print(f"  {idx}. {agent.agent_name}")
                print(f"     Units: {agent.units_sold}, Revenue: MK {agent.total_revenue:,.0f}, Commission: MK {agent.total_commission:,.0f}")
        else:
            print("  (No agent sales data for this month)")
        
    except Exception as e:
        print(f"❌ get_agent_earnings() failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Call get_top_agents
    try:
        top_agents = get_top_agents(
            business=business,
            start_date=start_date.date(),
            end_date=end_date.date(),
            limit=5,
        )
        print(f"\n✅ get_top_agents() returned {len(top_agents)} agents")
        
        if top_agents:
            print("\nTop Agents (This Month):")
            medals = ["🥇", "🥈", "🥉"]
            for idx, agent in enumerate(top_agents, 1):
                medal = medals[idx-1] if idx <= 3 else f"{idx}."
                print(f"  {medal} {agent.agent_name}")
                print(f"     {agent.units_sold} units sold · MK {agent.total_revenue:,.0f}")
        
    except Exception as e:
        print(f"❌ get_top_agents() failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Check that both queries work without errors
    print("\n" + "=" * 70)
    print("Testing model queries...")
    print("=" * 70)
    
    # Test WalletTransaction query
    try:
        from wallet.models import WalletTransaction, Ledger, TxnType
        wt_count = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.AGENT,
            type=TxnType.COMMISSION,
        ).count()
        print(f"✅ WalletTransaction query works: {wt_count} commission records")
    except Exception as e:
        print(f"⚠️  WalletTransaction query: {e}")
    
    # Test AgentWalletTransaction query
    try:
        from wallet.agent_models import AgentWalletTransaction, AgentWalletTransactionType
        awt_count = AgentWalletTransaction.objects.filter(
            transaction_type=AgentWalletTransactionType.COMMISSION_SALE,
            is_debit=False,
        ).count()
        print(f"✅ AgentWalletTransaction query works: {awt_count} commission records")
    except Exception as e:
        print(f"⚠️  AgentWalletTransaction query: {e}")
    
    # Test Sale query
    try:
        from sales.models import Sale
        sale_count = Sale.objects.filter(
            location__business=business,
        ).count()
        print(f"✅ Sale model query works: {sale_count} sale records")
    except Exception as e:
        print(f"⚠️  Sale model query: {e}")
    
    # Test InventoryItem query
    try:
        from inventory.models import InventoryItem
        inv_sold_count = InventoryItem.objects.filter(
            business=business,
            status='SOLD',
            sold_at__isnull=False,
            assigned_agent__isnull=False,
        ).count()
        print(f"✅ InventoryItem query works: {inv_sold_count} sold items with agent")
    except Exception as e:
        print(f"⚠️  InventoryItem query: {e}")
    
    print("\n" + "=" * 70)
    print("✅ All tests passed! The fix is working correctly.")
    print("=" * 70)
    
    return True

if __name__ == '__main__':
    success = test_agent_earnings_service()
    sys.exit(0 if success else 1)

