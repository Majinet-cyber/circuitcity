"""
Test suite for Recurring Costs (Problem B fix).

This test ensures that:
1. Saving a recurring cost creates a template (is_recurring=True)
2. Recurring costs auto-generate monthly instances
3. No duplicates are created (idempotent)
4. Default recurring cost templates are seeded for gym businesses
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business, Membership
from inventory.business_kinds import BusinessKind
from wallet.models import WalletTransaction, Ledger, TxnType
from wallet.services_costs import add_business_cost
from wallet.utils_costs import ensure_monthly_recurring_costs

User = get_user_model()


class RecurringCostSaveTestCase(TestCase):
    """Test that recurring cost save creates correct record type."""
    
    def setUp(self):
        """Set up test business and user."""
        self.business = Business.objects.create(
            name="Test Business RC",
            kind=BusinessKind.GYM,
            status="ACTIVE",
        )
        
        self.user = User.objects.create_user(
            username="rcmanager",
            email="rc@test.com",
            password="testpass123",
        )
        
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )
    
    def test_recurring_cost_service_creates_template(self):
        """Test that add_business_cost with is_recurring=True creates a recurring template."""
        cost = add_business_cost(
            business=self.business,
            name="Monthly Rent",
            amount=Decimal("100000.00"),
            cost_category="fixed",
            is_recurring=True,
            effective_date=timezone.localdate(),
            created_by=self.user,
            note="Office rent"
        )
        
        # Verify the cost is a recurring template
        self.assertTrue(cost.is_recurring, "Cost should be marked as recurring")
        self.assertEqual(cost.type, TxnType.COST_RECURRING, "Cost type should be COST_RECURRING")
        self.assertEqual(cost.ledger, Ledger.COMPANY, "Cost should use COMPANY ledger")
        self.assertEqual(cost.business, self.business, "Cost should be linked to business")
        self.assertEqual(cost.amount, Decimal("-100000.00"), "Cost should be negative (expense)")
        self.assertIsNotNone(cost.effective_from, "Recurring cost should have effective_from date")
    
    def test_once_off_cost_service_creates_instance(self):
        """Test that add_business_cost with is_recurring=False creates a once-off instance."""
        cost = add_business_cost(
            business=self.business,
            name="One-time Equipment",
            amount=Decimal("50000.00"),
            cost_category="variable",
            is_recurring=False,
            effective_date=timezone.localdate(),
            created_by=self.user,
        )
        
        # Verify the cost is a once-off instance
        self.assertFalse(cost.is_recurring, "Cost should NOT be marked as recurring")
        self.assertEqual(cost.type, TxnType.COST_ONCE_OFF, "Cost type should be COST_ONCE_OFF")
        self.assertIsNone(cost.effective_from, "Once-off cost should NOT have effective_from")
    
    def test_recurring_cost_view_post(self):
        """Test that the recurring cost creation view correctly saves recurring costs."""
        self.client.login(username="rcmanager", password="testpass123")
        self.user.active_business = self.business
        self.user.save()
        
        # POST to create recurring cost
        response = self.client.post(
            "/wallet/admin/costs/new/",
            data={
                "name": "Internet Bill",
                "amount": "20000",
                "cost_category": "fixed",
                "is_recurring": "on",  # Checkbox checked
                "effective_date": timezone.localdate().isoformat(),
                "note": "Monthly internet"
            },
            follow=False
        )
        
        # Should redirect on success
        self.assertEqual(response.status_code, 302, "Should redirect after successful creation")
        
        # Verify the cost was created as recurring
        cost = WalletTransaction.objects.filter(
            business=self.business,
            note__icontains="Internet Bill"
        ).first()
        
        self.assertIsNotNone(cost, "Cost should be created")
        self.assertTrue(cost.is_recurring, "Cost should be marked as recurring (BUG FIX VERIFICATION)")
        self.assertEqual(cost.type, TxnType.COST_RECURRING, "Cost type should be COST_RECURRING")


class RecurringCostAutoGenerationTestCase(TestCase):
    """Test recurring cost monthly auto-generation (idempotent)."""
    
    def setUp(self):
        """Set up test business with recurring cost template."""
        self.business = Business.objects.create(
            name="Test Business AG",
            kind=BusinessKind.GYM,
            status="ACTIVE",
        )
        
        self.user = User.objects.create_user(
            username="agmanager",
            email="ag@test.com",
            password="testpass123",
        )
        
        # Create a recurring cost template
        self.template = WalletTransaction.objects.create(
            business=self.business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            amount=Decimal("-100000.00"),
            note="Monthly Rent Template",
            effective_date=timezone.localdate(),
            effective_from=timezone.localdate().replace(day=1),
            is_recurring=True,
            created_by=self.user,
            meta={
                'cost_category': 'fixed',
                'cost_name': 'Rent',
                'recurrence_day': 1,  # Due on 1st of each month
            }
        )
    
    def test_auto_generation_creates_monthly_instance(self):
        """Test that ensure_monthly_recurring_costs creates a monthly instance."""
        today = timezone.localdate()
        month_start = date(today.year, today.month, 1)
        
        # Verify template exists and is set up correctly
        self.assertTrue(self.template.is_recurring, "Template should be marked as recurring")
        self.assertEqual(self.template.type, TxnType.COST_RECURRING, "Template should have COST_RECURRING type")
        self.assertIsNotNone(self.template.effective_from, "Template should have effective_from")
        self.assertLessEqual(
            self.template.effective_from,
            month_start,
            "Template effective_from should be <= month_start for auto-generation to work"
        )
        
        # Count existing instances before generation
        instances_before = WalletTransaction.objects.filter(
            business=self.business,
            type=TxnType.COST_RECURRING,
            is_recurring=False,
            effective_date__year=today.year,
            effective_date__month=today.month,
        ).count()
        
        # Run auto-generation
        created_count = ensure_monthly_recurring_costs(self.business, month_start)
        
        # Should create one instance
        self.assertGreater(created_count, 0, f"Should create at least one instance (template effective_from={self.template.effective_from}, month_start={month_start})")
        
        # Verify instance was created
        instances_after = WalletTransaction.objects.filter(
            business=self.business,
            type=TxnType.COST_RECURRING,
            is_recurring=False,
            effective_date__year=today.year,
            effective_date__month=today.month,
        ).count()
        
        self.assertEqual(
            instances_after,
            instances_before + 1,
            "Should create exactly one new instance"
        )
    
    def test_auto_generation_idempotent(self):
        """Test that running auto-generation twice does NOT create duplicates."""
        today = timezone.localdate()
        month_start = date(today.year, today.month, 1)
        
        # Run auto-generation twice
        created_count_1 = ensure_monthly_recurring_costs(self.business, month_start)
        created_count_2 = ensure_monthly_recurring_costs(self.business, month_start)
        
        # First run should create instances
        self.assertGreater(created_count_1, 0, "First run should create instances")
        
        # Second run should NOT create duplicates
        self.assertEqual(created_count_2, 0, "Second run should NOT create duplicates (idempotent)")
        
        # Verify only one instance exists
        instances = WalletTransaction.objects.filter(
            business=self.business,
            type=TxnType.COST_RECURRING,
            is_recurring=False,
            effective_date__year=today.year,
            effective_date__month=today.month,
        )
        
        self.assertEqual(instances.count(), 1, "Should have exactly one instance (no duplicates)")
    
    def test_auto_generation_next_month(self):
        """Test that auto-generation creates new instance for next month."""
        today = timezone.localdate()
        month_start = date(today.year, today.month, 1)
        
        # Generate for this month
        created_this_month = ensure_monthly_recurring_costs(self.business, month_start)
        self.assertGreater(created_this_month, 0, "Should create instance for this month")
        
        # Calculate next month
        if today.month == 12:
            next_month_start = date(today.year + 1, 1, 1)
        else:
            next_month_start = date(today.year, today.month + 1, 1)
        
        # Generate for next month
        created_next_month = ensure_monthly_recurring_costs(self.business, next_month_start)
        self.assertGreater(created_next_month, 0, "Should create instance for next month")
        
        # Verify two instances exist (one per month)
        total_instances = WalletTransaction.objects.filter(
            business=self.business,
            type=TxnType.COST_RECURRING,
            is_recurring=False,
        ).count()
        
        self.assertEqual(total_instances, 2, "Should have instances for both months")


class DefaultRecurringCostsSeededTestCase(TestCase):
    """Test that default recurring cost templates are seeded for gym businesses."""
    
    def test_seed_default_recurring_costs(self):
        """Test that seed_default_recurring_cost_templates creates default templates."""
        from wallet.utils_costs import seed_default_recurring_cost_templates
        
        business = Business.objects.create(
            name="New Gym Business Seed",
            kind=BusinessKind.GYM,
            status="ACTIVE",
        )
        
        user = User.objects.create_user(username="seedtest", password="test")
        
        # Seed default templates
        created_count = seed_default_recurring_cost_templates(business, user)
        
        # Should create at least 7 templates (Rentals, Transport, Utilities, Internet, Salaries, Security, Cleaning)
        self.assertGreaterEqual(created_count, 7, "Should create at least 7 default templates")
        
        # Verify templates exist
        templates = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            is_recurring=True,
        )
        
        self.assertGreaterEqual(templates.count(), 7, "Should have at least 7 templates in database")
        
        # Verify expected template names exist
        template_names = list(templates.values_list('note', flat=True))
        expected_names = ["Rentals", "Transport", "Utilities", "Internet", "Salaries", "Security", "Cleaning"]
        
        for expected_name in expected_names:
            self.assertIn(expected_name, template_names, f"Template '{expected_name}' should be seeded")
        
        # Verify templates are marked as seeded
        rentals_template = templates.filter(note="Rentals").first()
        self.assertIsNotNone(rentals_template, "Rentals template should exist")
        self.assertEqual(rentals_template.meta.get('seeded'), True, "Template should be marked as seeded")
        self.assertEqual(rentals_template.meta.get('is_template'), True, "Template should be marked as is_template")
    
    def test_seed_idempotent(self):
        """Test that seeding twice does NOT create duplicates."""
        from wallet.utils_costs import seed_default_recurring_cost_templates
        
        business = Business.objects.create(
            name="Gym Business Idempotent",
            kind=BusinessKind.GYM,
            status="ACTIVE",
        )
        
        user = User.objects.create_user(username="idempotenttest", password="test")
        
        # Seed once
        created_count_1 = seed_default_recurring_cost_templates(business, user)
        self.assertGreater(created_count_1, 0, "First seeding should create templates")
        
        # Seed again
        created_count_2 = seed_default_recurring_cost_templates(business, user)
        self.assertEqual(created_count_2, 0, "Second seeding should NOT create duplicates (idempotent)")
        
        # Verify only one set of templates exists
        templates = WalletTransaction.objects.filter(
            business=business,
            ledger=Ledger.COMPANY,
            type=TxnType.COST_RECURRING,
            is_recurring=True,
        )
        
        # Count unique template names
        unique_names = templates.values_list('note', flat=True).distinct()
        self.assertEqual(
            templates.count(),
            len(unique_names),
            "Should have no duplicate template names"
        )

