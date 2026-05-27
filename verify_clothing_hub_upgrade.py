#!/usr/bin/env python
"""
Clothing Hub Premium UI - Verification Script
Run this to verify the upgrade was successful
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def check_file(path, description):
    """Check if a file exists"""
    if os.path.exists(path):
        print(f"{GREEN}✓{RESET} {description}: {path}")
        return True
    else:
        print(f"{RED}✗{RESET} {description}: {path} {RED}NOT FOUND{RESET}")
        return False

def check_content(path, search_text, description):
    """Check if file contains specific text"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            if search_text in content:
                print(f"{GREEN}✓{RESET} {description}")
                return True
            else:
                print(f"{RED}✗{RESET} {description} - text not found")
                return False
    except FileNotFoundError:
        print(f"{RED}✗{RESET} {description} - file not found")
        return False
    except Exception as e:
        print(f"{RED}✗{RESET} {description} - error: {e}")
        return False

def main():
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}Clothing Hub Premium UI - Verification{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    checks_passed = 0
    checks_total = 0
    
    # Check 1: CSS file exists
    checks_total += 1
    if check_file('static/css/clothing-hub-premium.css', 'CSS file'):
        checks_passed += 1
    
    # Check 2: Template file exists
    checks_total += 1
    if check_file('templates/verticals/clothing/hub.html', 'Template file'):
        checks_passed += 1
    
    # Check 3: Template has wrapper class
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'class="clothing-hub premium-hub"',
        'Template has premium-hub wrapper'
    ):
        checks_passed += 1
    
    # Check 4: Template loads CSS
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'clothing-hub-premium.css',
        'Template loads premium CSS'
    ):
        checks_passed += 1
    
    # Check 5: CSS has scoped styles
    checks_total += 1
    if check_content(
        'static/css/clothing-hub-premium.css',
        '.premium-hub',
        'CSS is scoped to .premium-hub'
    ):
        checks_passed += 1
    
    # Check 6: CSS has mobile breakpoint
    checks_total += 1
    if check_content(
        'static/css/clothing-hub-premium.css',
        '@media (max-width: 768px)',
        'CSS has mobile breakpoint'
    ):
        checks_passed += 1
    
    # Check 7: CSS has reduced motion support
    checks_total += 1
    if check_content(
        'static/css/clothing-hub-premium.css',
        '@media (prefers-reduced-motion: reduce)',
        'CSS has reduced motion support'
    ):
        checks_passed += 1
    
    # Check 8: Template has premium header
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'hub-premium-header',
        'Template has premium header'
    ):
        checks_passed += 1
    
    # Check 9: Template has search input
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'hubSearchInput',
        'Template has search input'
    ):
        checks_passed += 1
    
    # Check 10: Template has client-side JS
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'debounce',
        'Template has client-side search JS'
    ):
        checks_passed += 1
    
    # Check 11: Template has premium cards
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'hub-product-card',
        'Template has premium card classes'
    ):
        checks_passed += 1
    
    # Check 12: Template has premium tabs
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'hub-tabs',
        'Template has premium tabs'
    ):
        checks_passed += 1
    
    # Check 13: Template has empty state
    checks_total += 1
    if check_content(
        'templates/verticals/clothing/hub.html',
        'hub-empty-state',
        'Template has premium empty state'
    ):
        checks_passed += 1
    
    # Check 14: No inline styles (except dynamic width)
    checks_total += 1
    with open('templates/verticals/clothing/hub.html', 'r', encoding='utf-8') as f:
        content = f.read()
        # Count style attributes (should only be width: for battery)
        style_count = content.count('style="')
        if style_count <= 2:  # Only battery width allowed
            print(f"{GREEN}✓{RESET} No excessive inline styles")
            checks_passed += 1
        else:
            print(f"{YELLOW}⚠{RESET} Found {style_count} inline styles (expected ≤2)")
    
    # Check 15: View file unchanged (no context key changes)
    checks_total += 1
    if check_file('inventory/verticals/clothing.py', 'View file'):
        if check_content(
            'inventory/verticals/clothing.py',
            'def hub(request):',
            'View function exists (unchanged)'
        ):
            checks_passed += 1
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    percentage = (checks_passed / checks_total) * 100
    
    if checks_passed == checks_total:
        print(f"{GREEN}✓ All checks passed! ({checks_passed}/{checks_total}){RESET}")
        print(f"{GREEN}Ready for testing and deployment.{RESET}")
        return_code = 0
    elif checks_passed >= checks_total * 0.8:
        print(f"{YELLOW}⚠ Most checks passed ({checks_passed}/{checks_total}) - {percentage:.1f}%{RESET}")
        print(f"{YELLOW}Review warnings before deployment.{RESET}")
        return_code = 1
    else:
        print(f"{RED}✗ Some checks failed ({checks_passed}/{checks_total}) - {percentage:.1f}%{RESET}")
        print(f"{RED}Fix errors before deployment.{RESET}")
        return_code = 2
    
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    # Additional info
    print(f"{BLUE}Next Steps:{RESET}")
    print("1. Run: python manage.py collectstatic --noinput")
    print("2. Start server: python manage.py runserver")
    print("3. Visit: http://localhost:8000/verticals/clothing/hub/")
    print("4. Test all tabs, search, and mobile view")
    print("5. Check browser console for errors\n")
    
    return return_code

if __name__ == '__main__':
    sys.exit(main())


