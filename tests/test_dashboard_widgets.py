from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import timedelta
from tenants.models import Business
from inventory.models import Location, Product, InventoryItem, AgentProfile

User = get_user_model()

class TestDashboardWidgets(TestCase):
    """Test that main dashboard widgets return correct data."""
    
    def setUp(self):
        # Create business
        self.business = Business.objects.create(
            name="Test Widget Store",
            business_kind="phones",
            slug="test-widget-store",
        )
        
        # Create location
        self.location = Location.objects.create(
            business=self.business,
            name="Main Store",
            is_default=True,
        )
        
        # Create user (manager/admin)
        self.user = User.objects.create_user(
            username="manager",
            email="manager@example.com",
            password="password123",
            is_staff=True
        )
        # Create agent profile for user (needed for leaderboard logic sometimes)
        # Assuming AgentProfile might be needed or at least harmless
        AgentProfile.objects.create(
            user=self.user,
            location=self.location,
            sales_goal=1000
        )
        
        # Create phone product
        self.phone_product = Product.objects.create(
            code="TECNO-SP40",
            brand="TECNO",
            model="Spark 40",
            variant="4+128",
            cost_price=400000,
            sale_price=551500,
            business=self.business
        )
        
        # Setup client
        self.client = Client()
        self.client.force_login(self.user)
        
        # Set active business in session (simulating middleware/context)
        session = self.client.session
        session['active_business_id'] = self.business.id
        session.save()
        
        # Also inject business attribute onto request if middleware doesn't run in tests perfectly
        # But force_login + session usually works with the project's custom middleware
    
    def test_sales_trend_including_proxy(self):
        """Sales trend API proxy should return formatted data when there are sales."""
        from sales.models import Sale
        
        # Create 2 sold phone items today WITH Sales records
        now = timezone.now()
        for i in range(2):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.phone_product,
                current_location=self.location,
                assigned_agent=self.user,
                status='SOLD',
                sold_at=now,
                sold_price=Decimal('551500'),
            )
            # Must create Sale record as API depends on it
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=now.date(),
                price=Decimal('551500'),
                payment_method='CASH'
            )
        
        # Call the dashboard sales trend API (the main dashboard one)
        url = reverse('dashboard:sales_trend')
        response = self.client.get(url, {'period': 'month', 'metric': 'count'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Should have labels and values (main dashboard format)
        self.assertIn('labels', data)
        self.assertIn('values', data)
        self.assertTrue(len(data['labels']) > 0)
        
        # Total count should be 2
        total_count = sum(data['values'])
        self.assertEqual(total_count, 2)

        # Test Amount metric
        response_amt = self.client.get(url, {'period': 'month', 'metric': 'amount'})
        data_amt = response_amt.json()
        total_amt = sum(data_amt['values'])
        self.assertEqual(total_amt, 1103000)  # 551500 * 2

    def test_top_models_proxy(self):
        """Top models API proxy should return TECNO Spark 40 with 2 units."""
        from sales.models import Sale
        
        # Create 2 sold TECNO Spark 40 phones
        for i in range(2):
            item = InventoryItem.objects.create(
                business=self.business,
                product=self.phone_product,
                current_location=self.location,
                assigned_agent=self.user,
                status='SOLD',
                sold_at=timezone.now(),
                sold_price=Decimal('551500'),
            )
            Sale.objects.create(
                item=item,
                agent=self.user,
                location=self.location,
                sold_at=timezone.now().date(),
                price=Decimal('551500'),
                payment_method='CASH'
            )
        
        url = reverse('dashboard:top_models')
        response = self.client.get(url, {'period': 'month'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIn('labels', data)
        self.assertIn('values', data)
        
        # Should have at least one model
        self.assertTrue(len(data['labels']) >= 1)
        
        # Check content
        if len(data['values']) > 0:
            self.assertEqual(data['values'][0], 2)
    
    def test_agent_leaderboard_includes_manager(self):
        """Agent leaderboard should show manager if they're the only seller."""
        # Ensure manager has NO AgentProfile to test the fallback logic
        AgentProfile.objects.filter(user=self.user).delete()
        
        # Manager makes 2 sales
        for i in range(2):
            InventoryItem.objects.create(
                business=self.business,
                product=self.phone_product,
                current_location=self.location,
                assigned_agent=self.user,  # Manager is the seller
                status='SOLD',
                sold_at=timezone.now(),
                sold_price=Decimal('551500'),
            )
            # Note: Leaderboard uses InventoryItem directly, so Sale creation is optional here
            # but good practice to keep consistent if logic changes to use Sale
        
        # Navigate to main dashboard page
        url = reverse('dashboard:home')
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Check context has agent_leaderboard with at least one entry
        self.assertIn('agent_leaderboard', response.context)
        leaderboard = response.context['agent_leaderboard']
        
        self.assertTrue(len(leaderboard) >= 1)
        
        # First entry should be rank 1 with 2 units
        first_agent = leaderboard[0]
        self.assertEqual(first_agent['rank'], 1)
        self.assertEqual(first_agent['units'], 2)
        self.assertEqual(first_agent['amount'], 1103000)
