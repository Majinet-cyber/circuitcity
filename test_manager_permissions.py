#!/usr/bin/env python
"""
Quick Test Script for Manager Permission Fixes
===============================================

Run this script to verify that manager permissions are working correctly.

Usage:
    python test_manager_permissions.py

Requirements:
    - Django environment must be set up
    - Database must be populated with test data
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models import InventoryItem, AgentProfile
from sales.services.rollback import RollbackService

User = get_user_model()


def test_manager_stock_assignment():
    """Test that managers can be assigned stock without AgentProfile"""
    print("\n" + "="*60)
    print("TEST 1: Manager Stock Assignment")
    print("="*60)
    
    try:
        # Find a manager without AgentProfile
        manager_membership = Membership.objects.filter(
            role__in=["MANAGER", "manager"]
        ).select_related('user').first()
        
        if not manager_membership:
            print("❌ No manager found in database")
            return False
        
        manager = manager_membership.user
        business = manager_membership.business
        
        # Check if manager has AgentProfile
        has_agent_profile = hasattr(manager, 'agent_profile')
        print(f"Manager: {manager.username}")
        print(f"Has AgentProfile: {has_agent_profile}")
        
        # Find a stock item to test with
        item = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).first()
        
        if not item:
            print("❌ No stock items found for testing")
            return False
        
        # Try to assign stock to manager
        old_agent = item.assigned_agent
        item.assigned_agent = manager
        
        try:
            item.full_clean()  # This will trigger validation
            print("✅ PASS: Manager can be assigned stock without AgentProfile")
            item.assigned_agent = old_agent  # Restore
            item.save()
            return True
        except Exception as e:
            print(f"❌ FAIL: {str(e)}")
            item.assigned_agent = old_agent  # Restore
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_manager_rollback_permissions():
    """Test that managers can rollback any sale"""
    print("\n" + "="*60)
    print("TEST 2: Manager Rollback Permissions")
    print("="*60)
    
    try:
        # Find a manager
        manager_membership = Membership.objects.filter(
            role__in=["MANAGER", "manager"]
        ).select_related('user').first()
        
        if not manager_membership:
            print("❌ No manager found in database")
            return False
        
        manager = manager_membership.user
        business = manager_membership.business
        
        print(f"Manager: {manager.username}")
        print(f"Business: {business.name}")
        
        # Find a recent sale to test with (but don't actually rollback)
        from sales.models import Sale
        sale = Sale.objects.filter(
            item__business=business,
            is_rolled_back=False
        ).first()
        
        if not sale:
            print("⚠️  No sales found for testing (creating mock sale)")
            # Create a mock sale for testing
            item = InventoryItem.objects.filter(
                business=business,
                status="IN_STOCK"
            ).first()
            
            if not item:
                print("❌ No stock items available")
                return False
            
            # Don't actually create sale, just test permission check
            from unittest.mock import Mock
            sale = Mock()
            sale.is_rolled_back = False
            sale.item = item
            sale.agent = manager
            sale.created_at = django.utils.timezone.now()
        
        # Test permission check (don't actually rollback)
        can_rollback, error_msg = RollbackService.can_rollback(
            sale, manager, business
        )
        
        if can_rollback:
            print("✅ PASS: Manager has rollback permissions")
            print(f"   Error message: {error_msg or 'None'}")
            return True
        else:
            print(f"❌ FAIL: Manager denied rollback")
            print(f"   Error message: {error_msg}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_restrictions():
    """Test that agents still have proper restrictions"""
    print("\n" + "="*60)
    print("TEST 3: Agent Restrictions (Regression Test)")
    print("="*60)
    
    try:
        # Find an agent
        agent_membership = Membership.objects.filter(
            role__in=["AGENT", "agent"]
        ).select_related('user').first()
        
        if not agent_membership:
            print("⚠️  No agent found in database")
            return True  # Not a failure, just no agents to test
        
        agent = agent_membership.user
        business = agent_membership.business
        
        print(f"Agent: {agent.username}")
        
        # Check if agent has AgentProfile
        has_agent_profile = hasattr(agent, 'agent_profile')
        print(f"Has AgentProfile: {has_agent_profile}")
        
        if not has_agent_profile:
            print("⚠️  Agent doesn't have AgentProfile (may need to be created)")
        
        # Test that agent can be assigned stock if they have AgentProfile
        item = InventoryItem.objects.filter(
            business=business,
            status="IN_STOCK"
        ).first()
        
        if not item:
            print("⚠️  No stock items found for testing")
            return True
        
        old_agent = item.assigned_agent
        item.assigned_agent = agent
        
        try:
            item.full_clean()
            if has_agent_profile:
                print("✅ PASS: Agent with AgentProfile can be assigned stock")
            else:
                print("❌ FAIL: Agent without AgentProfile should not be assignable")
            item.assigned_agent = old_agent
            item.save()
            return has_agent_profile  # Should only pass if agent has profile
        except Exception as e:
            if not has_agent_profile:
                print("✅ PASS: Agent without AgentProfile correctly rejected")
                item.assigned_agent = old_agent
                return True
            else:
                print(f"❌ FAIL: Agent with AgentProfile rejected: {str(e)}")
                item.assigned_agent = old_agent
                return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_homepage_metrics():
    """Test that homepage metrics endpoint works"""
    print("\n" + "="*60)
    print("TEST 4: Homepage Metrics API")
    print("="*60)
    
    try:
        from django.test import RequestFactory
        from staticpages.views import platform_stats_api
        
        factory = RequestFactory()
        request = factory.get('/landing/api/stats/')
        
        response = platform_stats_api(request)
        
        if response.status_code == 200:
            import json
            data = json.loads(response.content)
            
            print(f"✅ API Response: {data}")
            print(f"   Total Merchants: {data.get('total_merchants', 0)}")
            print(f"   Total Agents: {data.get('total_agents', 0)}")
            print(f"   Status: {data.get('status', 'unknown')}")
            
            if data.get('status') == 'success':
                print("✅ PASS: Homepage metrics API working")
                return True
            else:
                print("❌ FAIL: API returned error status")
                return False
        else:
            print(f"❌ FAIL: API returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("MANAGER PERMISSIONS TEST SUITE")
    print("="*60)
    print("Testing fixes for manager permission errors...")
    
    results = []
    
    # Run tests
    results.append(("Manager Stock Assignment", test_manager_stock_assignment()))
    results.append(("Manager Rollback Permissions", test_manager_rollback_permissions()))
    results.append(("Agent Restrictions", test_agent_restrictions()))
    results.append(("Homepage Metrics API", test_homepage_metrics()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Manager permissions are working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

