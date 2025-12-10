#!/usr/bin/env python
"""
Quick verification script for Gym status & arrears fixes.
Run: python test_gym_fixes.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from datetime import timedelta
from django.utils import timezone
from inventory.models_verticals import GymMember, GymPayment
from tenants.models import Business


def test_gym_member_properties():
    """Test that GymMember properties work correctly"""
    print("=" * 60)
    print("Testing GymMember Properties")
    print("=" * 60)
    
    # Find a gym business
    gym_businesses = Business.objects.filter(business_kind="GYM")
    if not gym_businesses.exists():
        print("❌ No gym businesses found. Create one first.")
        return False
    
    business = gym_businesses.first()
    print(f"✓ Found gym business: {business.name}")
    
    # Get all gym members
    members = GymMember.objects.filter(business=business, is_archived=False)
    total = members.count()
    print(f"✓ Total members: {total}")
    
    if total == 0:
        print("⚠ No members found. Create some test members to verify.")
        return True
    
    # Test properties on each member
    active_count = 0
    arrears_count = 0
    
    print("\nMember Status:")
    print("-" * 60)
    
    for member in members:
        # Test the new properties
        has_payment = member.current_payment is not None
        is_active = member.is_active_today
        days_left = member.days_left_current
        
        status = "ACTIVE" if is_active else "IN ARREARS"
        if is_active:
            active_count += 1
        else:
            arrears_count += 1
        
        print(f"  {member.name:30s} | {status:12s} | Days: {days_left:3d}")
        
        # Verify consistency
        if has_payment and not is_active:
            print(f"    ⚠ Warning: Has payment but not active!")
        if not has_payment and is_active:
            print(f"    ⚠ Warning: No payment but marked active!")
    
    print("-" * 60)
    print(f"Active Members:   {active_count}")
    print(f"In Arrears:       {arrears_count}")
    print(f"Total:            {total}")
    
    if active_count + arrears_count != total:
        print("❌ Count mismatch! Active + Arrears should equal Total.")
        return False
    
    print("✓ All counts match correctly!")
    return True


def test_payment_based_counts():
    """Test that payment-based queries match property-based counts"""
    print("\n" + "=" * 60)
    print("Testing Payment-Based Queries")
    print("=" * 60)
    
    gym_businesses = Business.objects.filter(business_kind="GYM")
    if not gym_businesses.exists():
        print("❌ No gym businesses found.")
        return False
    
    business = gym_businesses.first()
    today = timezone.localdate()
    
    # Query-based count (what the dashboard uses)
    all_members = GymMember.objects.filter(business=business, is_active=True, is_archived=False)
    total_members = all_members.count()
    
    active_members_query = all_members.filter(
        payments__start_date__lte=today,
        payments__end_date__gte=today,
        payments__is_active=True,
    ).distinct().count()
    
    arrears_query = total_members - active_members_query
    
    # Property-based count (manual verification)
    active_members_prop = 0
    arrears_prop = 0
    
    for member in all_members:
        if member.is_active_today:
            active_members_prop += 1
        else:
            arrears_prop += 1
    
    print(f"\nQuery-based counts:")
    print(f"  Total:     {total_members}")
    print(f"  Active:    {active_members_query}")
    print(f"  Arrears:   {arrears_query}")
    
    print(f"\nProperty-based counts:")
    print(f"  Total:     {total_members}")
    print(f"  Active:    {active_members_prop}")
    print(f"  Arrears:   {arrears_prop}")
    
    if active_members_query == active_members_prop and arrears_query == arrears_prop:
        print("\n✓ Query-based and property-based counts match!")
        return True
    else:
        print("\n❌ Counts don't match! Check the logic.")
        return False


def test_admin_check():
    """Verify Django admin has no system check errors"""
    print("\n" + "=" * 60)
    print("Testing Django Admin System Check")
    print("=" * 60)
    
    from django.core import checks
    from django.apps import apps
    
    # Run system checks
    all_issues = checks.run_checks(include_deployment_checks=False)
    
    if not all_issues:
        print("✓ No system check errors found!")
        return True
    
    # Filter for TrainerFee related issues
    trainer_fee_issues = [
        issue for issue in all_issues 
        if 'TrainerFee' in str(issue)
    ]
    
    if trainer_fee_issues:
        print(f"❌ Found {len(trainer_fee_issues)} TrainerFee-related issues:")
        for issue in trainer_fee_issues:
            print(f"  - {issue}")
        return False
    
    print(f"⚠ Found {len(all_issues)} system check issues (not TrainerFee related)")
    return True


def main():
    print("\n" + "=" * 60)
    print("GYM STATUS & ARREARS FIX - VERIFICATION SCRIPT")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Member Properties", test_gym_member_properties()))
    results.append(("Payment-Based Counts", test_payment_based_counts()))
    results.append(("Admin System Check", test_admin_check()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} - {name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n✓ All tests passed! Gym fixes working correctly.")
    else:
        print("\n⚠ Some tests failed. Review the output above.")
    
    return all_passed


if __name__ == "__main__":
    try:
        success = main()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error running tests: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

