#!/usr/bin/env python
"""
Quick verification script for invite acceptance flow fixes.
Run this to check that all the fixes are in place.
"""

import os
import sys

def check_file_contains(filepath, pattern, description):
    """Check if a file contains a specific pattern."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            if pattern in content:
                print(f"✅ {description}")
                return True
            else:
                print(f"❌ {description}")
                return False
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        return False
    except Exception as e:
        print(f"❌ Error checking {filepath}: {e}")
        return False


def main():
    print("=" * 70)
    print("INVITE FLOW FIXES VERIFICATION")
    print("=" * 70)
    print()
    
    checks_passed = 0
    total_checks = 0
    
    # Check 1: Form has defensive email handling
    total_checks += 1
    if check_file_contains(
        'tenants/forms.py',
        'except (AttributeError, KeyError):',
        "Form has defensive email extraction"
    ):
        checks_passed += 1
    
    # Check 2: View has error handling around form creation
    total_checks += 1
    if check_file_contains(
        'tenants/views_invites.py',
        'Error creating form for invite',
        "View catches form creation errors"
    ):
        checks_passed += 1
    
    # Check 3: View has error handling around email extraction
    total_checks += 1
    if check_file_contains(
        'tenants/views_invites.py',
        'Error extracting email for invite',
        "View catches email extraction errors"
    ):
        checks_passed += 1
    
    # Check 4: View has error handling around user creation
    total_checks += 1
    if check_file_contains(
        'tenants/views_invites.py',
        'Error creating user for invite',
        "View catches user creation errors"
    ):
        checks_passed += 1
    
    # Check 5: View has error handling around login
    total_checks += 1
    if check_file_contains(
        'tenants/views_invites.py',
        'Error logging in user for invite',
        "View catches login errors"
    ):
        checks_passed += 1
    
    # Check 6: View sets active_tab in context
    total_checks += 1
    if check_file_contains(
        'tenants/views_invites.py',
        '"active_tab": ""',
        "View sets active_tab to avoid template warnings"
    ):
        checks_passed += 1
    
    # Check 7: Template has CSRF token
    total_checks += 1
    if check_file_contains(
        'templates/tenants/invite_accept.html',
        '{% csrf_token %}',
        "Template includes CSRF token"
    ):
        checks_passed += 1
    
    # Check 8: Template has proper form structure
    total_checks += 1
    if check_file_contains(
        'templates/tenants/invite_accept.html',
        'method="post"',
        "Template has POST form"
    ):
        checks_passed += 1
    
    print()
    print("=" * 70)
    print(f"RESULTS: {checks_passed}/{total_checks} checks passed")
    print("=" * 70)
    print()
    
    if checks_passed == total_checks:
        print("✅ All fixes are in place!")
        print()
        print("Next steps:")
        print("1. Start the dev server: python manage.py runserver")
        print("2. Login as MANAGER and create an agent invite")
        print("3. Open the invite link in an incognito window")
        print("4. Fill out and submit the form")
        print("5. Verify no 500 errors, no CSRF errors")
        print("6. Check that user + membership are created")
        print()
        print("See INVITE_FLOW_FIXES.md for detailed testing checklist.")
        return 0
    else:
        print(f"⚠️  {total_checks - checks_passed} checks failed")
        print("Please review the changes and ensure all fixes are applied.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

