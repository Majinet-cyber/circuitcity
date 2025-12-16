#!/usr/bin/env python
"""
Verification script for Signup Wizard Skip & Gym Analytics implementation.
Runs basic checks to ensure features are working as expected.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")
django.setup()

from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models_verticals import GymMember, GymPayment
from inventory.analytics.adapters.gym import GymAdapter
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

User = get_user_model()

def print_test(name, passed, details=""):
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {name}")
    if details:
        print(f"     {details}")

def test_signup_wizard_skip_button():
    """Test 1: Verify signup wizard step 3 has skip button in template."""
    print("\n=== Testing Signup Wizard Skip Button ===")
    
    try:
        from pathlib import Path
        template_path = Path("templates/accounts/signup_manager_wizard_step3.html")
        
        if not template_path.exists():
            print_test("Template exists", False, "Template file not found")
            return
        
        content = template_path.read_text(encoding='utf-8')
        
        # Check for skip button
        has_skip = 'value="skip"' in content or 'Skip for now' in content
        print_test("Skip button present", has_skip)
        
        # Check for disabled upload
        has_disabled = 'disabled' in content or 'coming soon' in content.lower()
        print_test("Logo upload disabled", has_disabled)
        
        # Check for three buttons (Back, Skip, Next)
        has_back = 'value="back"' in content
        has_next = 'value="next"' in content
        print_test("All three action buttons present", has_back and has_skip and has_next)
        
    except Exception as e:
        print_test("Template verification", False, str(e))

def test_signup_wizard_view_skip_handling():
    """Test 2: Verify view handles skip action."""
    print("\n=== Testing View Skip Action Handling ===")
    
    try:
        from pathlib import Path
        view_path = Path("circuitcity/accounts/views.py")
        
        if not view_path.exists():
            print_test("View file exists", False, "View file not found")
            return
        
        content = view_path.read_text()
        
        # Check for skip action handling
        has_skip_action = 'action == "skip"' in content
        print_test("Skip action handler present", has_skip_action)
        
        # Check for redirect to step 4
        has_redirect = 'step=4' in content
        print_test("Step 4 redirect present", has_redirect)
        
    except Exception as e:
        print_test("View verification", False, str(e))

def test_gym_adapter_returns_member_metrics():
    """Test 3: Verify GymAdapter returns member/payment metrics."""
    print("\n=== Testing Gym Adapter Metrics ===")
    
    try:
        # Create test gym business
        user = User.objects.create_user(
            username=f'testgym_{timezone.now().timestamp()}',
            email=f'testgym_{timezone.now().timestamp()}@test.com',
            password='testpass123'
        )
        business = Business.objects.create(
            name='Test Gym Verify',
            subdomain=f'testgymverify_{timezone.now().timestamp()}',
            kind='gym',
            owner=user,
        )
        
        adapter = GymAdapter()
        today = date.today()
        
        kpis = adapter.kpis(
            business=business,
            start_date=today - timedelta(days=30),
            end_date=today,
        )
        
        # Check for gym-specific metrics
        has_members = 'total_members' in kpis
        print_test("KPIs include total_members", has_members)
        
        has_active = 'active_memberships' in kpis
        print_test("KPIs include active_memberships", has_active)
        
        has_payments = 'payments_today' in kpis
        print_test("KPIs include payments_today", has_payments)
        
        has_revenue = 'revenue' in kpis
        print_test("KPIs include revenue", has_revenue)
        
        # Clean up
        business.delete()
        user.delete()
        
    except Exception as e:
        print_test("Gym adapter test", False, str(e))

def test_gym_dashboard_template_conditionals():
    """Test 4: Verify gym dashboard template shows correct metrics."""
    print("\n=== Testing Gym Dashboard Template ===")
    
    try:
        from pathlib import Path
        template_path = Path("templates/verticals/gym/dashboard.html")
        
        if not template_path.exists():
            print_test("Gym dashboard template exists", False, "Template not found")
            return
        
        content = template_path.read_text(encoding='utf-8')
        
        # Check for member metrics
        has_members = 'Total Members' in content or 'members' in content.lower()
        print_test("Template shows member metrics", has_members)
        
        # Check for payment/revenue metrics
        has_revenue = 'Revenue' in content or 'revenue' in content.lower()
        print_test("Template shows revenue metrics", has_revenue)
        
        # Check that stock metrics are NOT present
        has_stock = 'Stock Overview' in content or 'Stock Value' in content
        print_test("Template does NOT show stock metrics", not has_stock)
        
    except Exception as e:
        print_test("Gym dashboard template test", False, str(e))

def test_analytics_template_gym_conditionals():
    """Test 5: Verify analytics template conditionally hides stock for gym."""
    print("\n=== Testing Analytics Template Conditionals ===")
    
    try:
        from pathlib import Path
        template_path = Path("templates/inventory/analytics/dashboard.html")
        
        if not template_path.exists():
            print_test("Analytics template exists", False, "Template not found")
            return
        
        content = template_path.read_text(encoding='utf-8')
        
        # Check for gym conditionals
        has_gym_condition = 'vertical != \'gym\'' in content or "vertical != 'gym'" in content
        print_test("Template has gym conditionals", has_gym_condition)
        
        # Check for gym-specific sections
        has_gym_members = 'vertical == \'gym\' and \'members\'' in content or "vertical == 'gym' and 'members'" in content
        print_test("Template has gym member sections", has_gym_members)
        
    except Exception as e:
        print_test("Analytics template test", False, str(e))

def main():
    """Run all verification tests."""
    print("=" * 60)
    print("SIGNUP WIZARD SKIP & GYM ANALYTICS VERIFICATION")
    print("=" * 60)
    
    test_signup_wizard_skip_button()
    test_signup_wizard_view_skip_handling()
    test_gym_adapter_returns_member_metrics()
    test_gym_dashboard_template_conditionals()
    test_analytics_template_gym_conditionals()
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
    print("\nManual Testing Still Required:")
    print("1. Navigate to signup wizard and test skip button")
    print("2. Create/login to gym business and check dashboard")
    print("3. Verify analytics page shows gym metrics (not stock)")
    print("\nSee SIGNUP_WIZARD_GYM_ANALYTICS_IMPLEMENTATION.md for details.")

if __name__ == "__main__":
    main()

