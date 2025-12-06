# audit/tests.py
"""
Comprehensive tests for HQ Audit Logs functionality.
Tests cover log creation, filtering, export, and HQ staff activity tracking.
"""
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse

from audit.models import AuditLog
from audit.utils import log_hq_action, log_audit
from tenants.models import Business

User = get_user_model()


class AuditLogModelTest(TestCase):
    """Test the AuditLog model."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Test Business", slug="test-business")
        self.user = User.objects.create_user(username="staff_user", password="testpass123", is_staff=True)
    
    def test_audit_log_creation(self):
        """Test creating an audit log entry."""
        log = AuditLog.objects.create(
            business=self.business,
            user=self.user,
            entity="Business",
            entity_id=str(self.business.pk),
            action="VIEW_PAGE",
            message="Viewed business detail",
            ip="127.0.0.1",
            ua="Mozilla/5.0"
        )
        
        self.assertEqual(log.business, self.business)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, "VIEW_PAGE")
        self.assertEqual(log.entity, "Business")
        self.assertIsNotNone(log.created_at)
    
    def test_audit_log_ordering(self):
        """Test that audit logs are ordered by created_at descending."""
        old_log = AuditLog.objects.create(
            business=self.business,
            user=self.user,
            action="OLD_ACTION",
            entity="Test"
        )
        
        # Create a newer log
        new_log = AuditLog.objects.create(
            business=self.business,
            user=self.user,
            action="NEW_ACTION",
            entity="Test"
        )
        
        logs = list(AuditLog.objects.all())
        self.assertEqual(logs[0], new_log)  # Newest first
        self.assertEqual(logs[1], old_log)


class AuditUtilsTest(TestCase):
    """Test audit utility functions."""
    
    def setUp(self):
        self.business = Business.objects.create(name="Utils Test Business", slug="utils-test")
        self.user = User.objects.create_user(username="test_staff", password="testpass123", is_staff=True)
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_log_hq_action_creates_log(self):
        """Test that log_hq_action creates an audit log."""
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/hq/dashboard/')
        request.user = self.user
        
        log = log_hq_action(
            request,
            action="VIEW_PAGE",
            entity_type="HQ_DASHBOARD",
            message="Accessed HQ dashboard",
            business=self.business
        )
        
        self.assertIsNotNone(log)
        self.assertEqual(log.action, "VIEW_PAGE")
        self.assertEqual(log.entity, "HQ_DASHBOARD")
        self.assertEqual(log.message, "Accessed HQ dashboard")
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.business, self.business)
    
    def test_log_hq_action_handles_no_business(self):
        """Test that log_hq_action handles missing business gracefully."""
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/hq/dashboard/')
        request.user = self.user
        
        # Should use first available business or return None
        log = log_hq_action(
            request,
            action="TEST_ACTION",
            entity_type="TEST",
            message="Test with no business"
        )
        
        # Either creates log with first business or returns None
        self.assertTrue(log is None or isinstance(log, AuditLog))


class AuditLogViewTest(TestCase):
    """Test HQ audit log views."""
    
    def setUp(self):
        self.business = Business.objects.create(name="View Test Business", slug="view-test")
        self.staff_user = User.objects.create_user(
            username="hq_staff",
            password="testpass123",
            is_staff=True
        )
        self.normal_user = User.objects.create_user(
            username="normal_user",
            password="testpass123"
        )
        self.client = Client()
    
    def test_audit_log_list_requires_staff(self):
        """Test that audit log list requires staff permission."""
        # Try as normal user
        self.client.force_login(self.normal_user)
        response = self.client.get(reverse('audit:log_list'))
        
        # Should redirect or return 403
        self.assertIn(response.status_code, [302, 403])
        
        # Try as staff user
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('audit:log_list'))
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
    
    def test_audit_log_list_shows_staff_activity_only(self):
        """Test that audit log list shows only staff activity."""
        # Create logs for both staff and normal user
        staff_log = AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            action="VIEW_PAGE",
            entity="Test",
            message="Staff action"
        )
        
        normal_log = AuditLog.objects.create(
            business=self.business,
            user=self.normal_user,
            action="VIEW_PAGE",
            entity="Test",
            message="Normal user action"
        )
        
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('audit:log_list'))
        
        self.assertEqual(response.status_code, 200)
        logs = response.context['logs']
        
        # Should only contain staff log
        self.assertIn(staff_log, logs)
        self.assertNotIn(normal_log, logs)
    
    def test_audit_log_date_filtering(self):
        """Test filtering audit logs by date range."""
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        last_week = now - timedelta(days=7)
        
        # Create logs at different times
        old_log = AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            action="OLD_ACTION",
            entity="Test"
        )
        old_log.created_at = last_week
        old_log.save()
        
        new_log = AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            action="NEW_ACTION",
            entity="Test"
        )
        
        self.client.force_login(self.staff_user)
        
        # Filter to show only recent logs
        response = self.client.get(reverse('audit:log_list'), {
            'start_date': yesterday.strftime('%Y-%m-%d'),
            'end_date': now.strftime('%Y-%m-%d')
        })
        
        self.assertEqual(response.status_code, 200)
        logs = list(response.context['logs'])
        
        # Should only contain new log
        self.assertIn(new_log, logs)
        self.assertNotIn(old_log, logs)
    
    def test_audit_log_action_filtering(self):
        """Test filtering audit logs by action."""
        view_log = AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            action="VIEW_PAGE",
            entity="Test"
        )
        
        export_log = AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            action="EXPORT_CSV",
            entity="Test"
        )
        
        self.client.force_login(self.staff_user)
        
        # Filter by action
        response = self.client.get(reverse('audit:log_list'), {
            'action': 'EXPORT'
        })
        
        self.assertEqual(response.status_code, 200)
        logs = list(response.context['logs'])
        
        # Should only contain export log
        self.assertIn(export_log, logs)
        self.assertNotIn(view_log, logs)
    
    def test_audit_log_business_filtering(self):
        """Test filtering audit logs by business."""
        business2 = Business.objects.create(name="Business 2", slug="business-2")
        
        log1 = AuditLog.objects.create(
            business=self.business,
            user=self.staff_user,
            action="TEST",
            entity="Test"
        )
        
        log2 = AuditLog.objects.create(
            business=business2,
            user=self.staff_user,
            action="TEST",
            entity="Test"
        )
        
        self.client.force_login(self.staff_user)
        
        # Filter by business
        response = self.client.get(reverse('audit:log_list'), {
            'business': self.business.pk
        })
        
        self.assertEqual(response.status_code, 200)
        logs = list(response.context['logs'])
        
        # Should only contain log1
        self.assertIn(log1, logs)
        self.assertNotIn(log2, logs)
    
    def test_audit_log_csv_export(self):
        """Test exporting audit logs to CSV."""
        # Create some logs
        for i in range(5):
            AuditLog.objects.create(
                business=self.business,
                user=self.staff_user,
                action=f"ACTION_{i}",
                entity="Test",
                message=f"Test message {i}"
            )
        
        self.client.force_login(self.staff_user)
        
        # Request CSV export
        response = self.client.get(reverse('audit:log_list'), {
            'export': 'csv'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response.get('Content-Type', ''))
        self.assertIn('attachment', response.get('Content-Disposition', ''))
        
        # Check that CSV contains data
        content = response.content.decode('utf-8')
        self.assertIn('Date/Time', content)
        self.assertIn('Business', content)
        self.assertIn('Action', content)
        self.assertIn('Test message', content)
    
    def test_audit_log_pagination(self):
        """Test that audit logs are paginated."""
        # Create many logs
        for i in range(60):
            AuditLog.objects.create(
                business=self.business,
                user=self.staff_user,
                action=f"ACTION_{i}",
                entity="Test"
            )
        
        self.client.force_login(self.staff_user)
        
        # Get first page
        response = self.client.get(reverse('audit:log_list'))
        
        self.assertEqual(response.status_code, 200)
        logs = response.context['logs']
        
        # Should have pagination (default 50 per page)
        self.assertTrue(logs.has_other_pages())
        self.assertLessEqual(len(logs), 50)


class HQViewAuditIntegrationTest(TestCase):
    """Test that HQ views properly create audit logs."""
    
    def setUp(self):
        self.business = Business.objects.create(name="HQ Test Business", slug="hq-test", status="ACTIVE")
        self.staff_user = User.objects.create_user(
            username="hq_admin",
            password="testpass123",
            is_staff=True,
            is_superuser=True
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
    
    def test_hq_dashboard_creates_audit_log(self):
        """Test that accessing HQ dashboard creates an audit log."""
        initial_count = AuditLog.objects.filter(action="VIEW_PAGE", entity="HQ_DASHBOARD").count()
        
        response = self.client.get(reverse('hq:dashboard'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check that audit log was created
        final_count = AuditLog.objects.filter(action="VIEW_PAGE", entity="HQ_DASHBOARD").count()
        self.assertEqual(final_count, initial_count + 1)
        
        # Verify log details
        log = AuditLog.objects.filter(action="VIEW_PAGE", entity="HQ_DASHBOARD").latest('created_at')
        self.assertEqual(log.user, self.staff_user)
        self.assertIn("dashboard", log.message.lower())
    
    def test_hq_businesses_list_creates_audit_log(self):
        """Test that accessing businesses list creates an audit log."""
        initial_count = AuditLog.objects.filter(action="VIEW_PAGE", entity="BUSINESS_LIST").count()
        
        response = self.client.get(reverse('hq:businesses'))
        
        self.assertEqual(response.status_code, 200)
        
        # Check that audit log was created
        final_count = AuditLog.objects.filter(action="VIEW_PAGE", entity="BUSINESS_LIST").count()
        self.assertEqual(final_count, initial_count + 1)
    
    def test_hq_business_detail_creates_audit_log(self):
        """Test that viewing business detail creates an audit log."""
        initial_count = AuditLog.objects.filter(action="VIEW_PAGE", entity="Business").count()
        
        response = self.client.get(reverse('hq:business_detail', args=[self.business.pk]))
        
        self.assertEqual(response.status_code, 200)
        
        # Check that audit log was created
        final_count = AuditLog.objects.filter(action="VIEW_PAGE", entity="Business").count()
        self.assertEqual(final_count, initial_count + 1)
        
        # Verify log details
        log = AuditLog.objects.filter(action="VIEW_PAGE", entity="Business").latest('created_at')
        self.assertEqual(log.entity_id, str(self.business.pk))
        self.assertEqual(log.business, self.business)

