#!/usr/bin/env python
"""
Quick verification script for agent and dashboard fixes.
Run this to verify the fixes are in place without running full test suite.
"""
import os
import sys

def check_file_contains(filepath, search_strings):
    """Check if file contains all search strings."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        results = []
        for search_str in search_strings:
            found = search_str in content
            results.append((search_str, found))
        
        return results
    except FileNotFoundError:
        return [(f"File not found: {filepath}", False)]

def main():
    print("=" * 70)
    print("VERIFICATION: Agent Invite + Dashboard Chart Fixes")
    print("=" * 70)
    
    all_passed = True
    
    # Check 1: Dashboard views have @require_business
    print("\n[1] Checking dashboard chart APIs have @require_business decorator...")
    results = check_file_contains(
        'dashboard/views.py',
        [
            '@require_business\n@require_GET\ndef v2_sales_trend_data_proxy',
            '@require_business\n@require_GET\ndef v2_top_models_data_proxy',
        ]
    )
    for search, found in results:
        status = "✅ PASS" if found else "❌ FAIL"
        print(f"  {status}: {search[:50]}...")
        if not found:
            all_passed = False
    
    # Check 2: Manager views return temp password
    print("\n[2] Checking manager invite views return temp password...")
    results = check_file_contains(
        'tenants/views_manager.py',
        [
            'inv, temp_password = _safe_service_create_invite(',
            'generate_temp_password=True',
            'temp_password=',
        ]
    )
    for search, found in results:
        status = "✅ PASS" if found else "❌ FAIL"
        print(f"  {status}: {search[:50]}...")
        if not found:
            all_passed = False
    
    # Check 3: Suspend/restore views exist
    print("\n[3] Checking suspend/restore agent views exist...")
    results = check_file_contains(
        'tenants/views_manager.py',
        [
            'def suspend_agent(',
            'def restore_agent(',
            'def edit_agent_location(',
            'membership.status = "SUSPENDED"',
            'user.is_active = False',
        ]
    )
    for search, found in results:
        status = "✅ PASS" if found else "❌ FAIL"
        print(f"  {status}: {search[:50]}...")
        if not found:
            all_passed = False
    
    # Check 4: URLs for suspend/restore exist
    print("\n[4] Checking URL patterns for agent management...")
    results = check_file_contains(
        'tenants/urls.py',
        [
            'suspend_agent',
            'restore_agent',
            'edit_agent_location',
        ]
    )
    for search, found in results:
        status = "✅ PASS" if found else "❌ FAIL"
        print(f"  {status}: {search[:50]}...")
        if not found:
            all_passed = False
    
    # Check 5: Template shows password
    print("\n[5] Checking template displays temp password...")
    results = check_file_contains(
        'templates/tenants/manager_review_agents.html',
        [
            'temp_password',
            'Temporary Password',
            'Suspend',
            'Restore',
        ]
    )
    for search, found in results:
        status = "✅ PASS" if found else "❌ FAIL"
        print(f"  {status}: {search[:50]}...")
        if not found:
            all_passed = False
    
    # Check 6: Tests exist
    print("\n[6] Checking test files exist...")
    test_files = [
        'tests/test_agents_and_invites.py',
        'tests/test_dashboard_charts_fixed.py',
    ]
    for test_file in test_files:
        exists = os.path.exists(test_file)
        status = "✅ PASS" if exists else "❌ FAIL"
        print(f"  {status}: {test_file}")
        if not exists:
            all_passed = False
    
    # Check 7: Summary document exists
    print("\n[7] Checking summary document...")
    exists = os.path.exists('AGENT_FIXES_SUMMARY.md')
    status = "✅ PASS" if exists else "❌ FAIL"
    print(f"  {status}: AGENT_FIXES_SUMMARY.md")
    if not exists:
        all_passed = False
    
    # Final result
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL CHECKS PASSED - Fixes are in place!")
        print("\nNext steps:")
        print("1. Run: python manage.py migrate")
        print("2. Start server: python manage.py runserver")
        print("3. Test manually:")
        print("   - Go to /tenants/manager/agents/")
        print("   - Create an invite and see password + link")
        print("   - Go to /dashboard/ and see charts (no errors)")
        print("   - Suspend/restore agents from the table")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Review output above")
        return 1

if __name__ == '__main__':
    sys.exit(main())

