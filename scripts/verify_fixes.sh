#!/bin/bash
# Verification script for Legacy Blocking + Mobile Overflow fixes
# Run this after deployment to ensure both fixes are working

echo "================================================"
echo "Legacy Blocking + Mobile Overflow Fix Verification"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter for passed/failed tests
PASSED=0
FAILED=0

echo "Part A: Legacy Blocking Tests"
echo "------------------------------"

# Test 1: Run Django tests for legacy blocking
echo -n "Running Django legacy blocking tests... "
if python manage.py test inventory.tests.test_legacy_blocking --verbosity=0; then
    echo -e "${GREEN}✓ PASSED${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

echo ""
echo "Part B: Mobile Overflow Tests"
echo "-----------------------------"

# Test 2: Check if Cypress is available
if command -v npx &> /dev/null; then
    echo -n "Running Cypress mobile overflow tests... "
    if npx cypress run --spec cypress/e2e/mobile_dashboard_overflow.cy.js --headless --quiet; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠ Cypress not available (skip E2E tests)${NC}"
fi

echo ""
echo "================================================"
echo "Verification Summary"
echo "================================================"
echo -e "${GREEN}Passed: $PASSED${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED${NC}"
    exit 1
else
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
fi

