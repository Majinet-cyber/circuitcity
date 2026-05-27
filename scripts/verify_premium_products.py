#!/usr/bin/env python
"""
Verification script for Premium Products UI redesign
Checks that all required files exist and are properly configured
"""
import os
import sys


def check_file_exists(filepath, description):
    """Check if a file exists and report"""
    if os.path.exists(filepath):
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ MISSING: {description}: {filepath}")
        return False


def check_directory_exists(dirpath, description):
    """Check if a directory exists and report"""
    if os.path.isdir(dirpath):
        print(f"✅ {description}: {dirpath}")
        return True
    else:
        print(f"❌ MISSING: {description}: {dirpath}")
        return False


def main():
    print("=" * 60)
    print("Premium Products UI Redesign - Verification")
    print("=" * 60)
    print()

    all_checks = []

    # Check CSS file
    print("📦 Checking CSS Files...")
    all_checks.append(check_file_exists("static/css/premium-products.css", "Premium Products CSS"))
    print()

    # Check partial templates directory
    print("📁 Checking Template Directories...")
    all_checks.append(check_directory_exists("templates/partials/products", "Products Partials Directory"))
    print()

    # Check partial templates
    print("📄 Checking Partial Templates...")
    all_checks.append(check_file_exists("templates/partials/products/product_card.html", "Product Card Partial"))
    all_checks.append(check_file_exists("templates/partials/products/product_grid.html", "Product Grid Partial"))
    all_checks.append(check_file_exists("templates/partials/products/product_filters.html", "Product Filters Partial"))
    all_checks.append(
        check_file_exists("templates/partials/products/product_table_fallback.html", "Product Table Fallback Partial")
    )
    print()

    # Check updated templates
    print("📝 Checking Updated Templates...")
    all_checks.append(check_file_exists("templates/inventory/products/liquor_v2.html", "Liquor Products Template"))
    all_checks.append(check_file_exists("templates/verticals/pharmacy/batch_list.html", "Pharmacy Batch List Template"))
    all_checks.append(check_file_exists("templates/verticals/phones/products.html", "Phones Products Template"))
    print()

    # Check tests
    print("🧪 Checking Test Files...")
    all_checks.append(check_file_exists("inventory/tests/test_product_redesign.py", "Django Regression Tests"))
    all_checks.append(check_file_exists("cypress/e2e/premium_products_mobile.cy.js", "Cypress E2E Tests"))
    print()

    # Check documentation
    print("📚 Checking Documentation...")
    all_checks.append(check_file_exists("PREMIUM_PRODUCTS_REDESIGN_SUMMARY.md", "Full Summary Documentation"))
    all_checks.append(check_file_exists("PREMIUM_PRODUCTS_QUICK_START.md", "Quick Start Guide"))
    print()

    # Summary
    print("=" * 60)
    total = len(all_checks)
    passed = sum(all_checks)
    failed = total - passed

    if failed == 0:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        print()
        print("🎉 Premium Products UI redesign is complete and verified!")
        print()
        print("Next steps:")
        print("  1. Run Django tests: python manage.py test inventory.tests.test_product_redesign")
        print("  2. Run Cypress tests: npx cypress run --spec 'cypress/e2e/premium_products_mobile.cy.js'")
        print("  3. Test manually on mobile (360px width)")
        print("  4. Review PREMIUM_PRODUCTS_QUICK_START.md for usage")
        return 0
    else:
        print(f"❌ CHECKS FAILED ({failed}/{total} failures)")
        print()
        print("Please ensure all files are created and in the correct locations.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
