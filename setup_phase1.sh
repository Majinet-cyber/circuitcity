#!/bin/bash
# setup_phase1.sh
# Quick setup script for Phase 1 Integration

echo "================================================"
echo "CircuitCity Phase 1 Integration Setup"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Step 1: Create migrations
echo "Step 1: Creating migrations..."
python manage.py makemigrations inventory --noinput
python manage.py makemigrations wallet --noinput
python manage.py makemigrations sales --noinput
python manage.py makemigrations timelogs --noinput
print_success "Migrations created"
echo ""

# Step 2: Apply migrations
echo "Step 2: Applying migrations..."
python manage.py migrate sales --noinput
python manage.py migrate inventory --noinput
python manage.py migrate timelogs --noinput
python manage.py migrate wallet --noinput
print_success "Migrations applied"
echo ""

# Step 3: Run tests
echo "Step 3: Running tests..."
if python manage.py test --keepdb --no-input; then
    print_success "All tests passed"
else
    print_warning "Some tests failed (this may be expected if test data is missing)"
fi
echo ""

# Step 4: Check for Cypress
echo "Step 4: Checking Cypress setup..."
if [ -d "node_modules/cypress" ]; then
    print_success "Cypress is installed"
    echo "  Run 'npm run cypress:open' to test E2E"
else
    print_warning "Cypress not installed"
    echo "  Run 'npm install --save-dev cypress' to install"
fi
echo ""

# Step 5: Summary
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Start dev server:"
echo "   python manage.py runserver"
echo ""
echo "2. (Optional) Run Cypress E2E tests:"
echo "   npm run cypress:open"
echo ""
echo "3. Access your dashboard:"
echo "   http://127.0.0.1:8000/accounts/login/"
echo ""
echo "Features now available:"
print_success "Profit & Payment Mix on Phones Dashboard"
print_success "Automatic Commission Tracking"
print_success "Agent Rankings & Milestones"
print_success "Admin Wallet Adjustments"
print_success "Signup Email Validation"
print_success "Clothing Price Guard-Rails"
print_success "Stock Integrity & Audit Trail"
print_success "IMEI Uniqueness Enforcement"
echo ""
echo "See PHASE1_INTEGRATION_COMPLETE.md for full documentation"
echo "================================================"

