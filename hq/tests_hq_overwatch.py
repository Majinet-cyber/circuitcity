# hq/tests_hq_overwatch.py
"""
Tests for HQ Overwatch Admin functionality.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business, Membership
from billing.models import BusinessSubscription
from hq.models import SupportActionLog, SupportTicket, BusinessNote, SupportNote
from datetime import timedelta
from django.utils import timezone

User = get_user_model()


class HQPermissionsTestCase(TestCase):
    """Test HQ permissions and access control."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create HQ admin user (staff)
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()

        # Create regular business owner
        self.business_owner = User.objects.create_user(
            username="owner_business", email="owner@business.com", password="testpass123"
        )

        # Create test business
        self.business = Business.objects.create(
            name="Test Business", slug="test-business", created_by=self.business_owner, status="ACTIVE"
        )

        # Create membership (valid role is MANAGER or AGENT)
        Membership.objects.create(business=self.business, user=self.business_owner, role="MANAGER", status="ACTIVE")

    def test_non_hq_cannot_access_directory(self):
        """Non-HQ users should not access business directory."""
        self.client.force_login(self.business_owner)
        response = self.client.get(reverse("hq:business_directory"))
        self.assertNotEqual(response.status_code, 200)
        # Should redirect or return 403

    def test_hq_admin_can_access_directory(self):
        """HQ admin should access business directory."""
        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Directory")

    def test_hq_admin_can_access_command_center(self):
        """HQ admin should access business command center."""
        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("hq:business_command_center", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.business.name)

    def test_hq_admin_can_access_account_support(self):
        """HQ admin should access account support."""
        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("hq:account_support", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account & Login Support")


class SupportActionLogTestCase(TestCase):
    """Test SupportActionLog audit trail."""

    def setUp(self):
        """Set up test data."""
        self.hq_admin = User.objects.create_user(
            username="admin_hq", email="admin@hq.com", password="testpass123", is_staff=True
        )

        self.business = Business.objects.create(name="Test Business", slug="test-business", status="ACTIVE")

    def test_create_support_action_log(self):
        """Test creating a support action log entry."""
        # Create new instance (not via .create to avoid triggering save validation)
        log = SupportActionLog(
            actor=self.hq_admin,
            business=self.business,
            action_type="EXTEND_SUBSCRIPTION",
            reason="Customer requested extension",
            entity_type="Subscription",
            entity_id=str(self.business.id),
            payload_before={"days": 30},
            payload_after={"days": 60},
        )
        # Save should work for new records (no pk yet)
        log.save()

        self.assertEqual(log.actor, self.hq_admin)
        self.assertEqual(log.business, self.business)
        self.assertEqual(log.action_type, "EXTEND_SUBSCRIPTION")
        self.assertIsNotNone(log.created_at)

    def test_support_action_log_immutable(self):
        """Test that support action logs are immutable."""
        log = SupportActionLog(
            actor=self.hq_admin, business=self.business, action_type="UNLOCK_ACCOUNT", reason="Customer locked out"
        )
        log.save()  # Initial save works

        # Try to update the log (should raise error)
        with self.assertRaises(ValueError):
            log.reason = "Changed reason"
            log.save()


class SupportTicketTestCase(TestCase):
    """Test SupportTicket model."""

    def setUp(self):
        """Set up test data."""
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.save()

        self.business = Business.objects.create(name="Test Business", slug="test-business", status="ACTIVE")

    def test_create_support_ticket(self):
        """Test creating a support ticket."""
        ticket = SupportTicket.objects.create(
            business=self.business,
            title="Login Issue",
            description="User cannot log in",
            category="login",
            priority="high",
            status="open",
        )

        self.assertIsNotNone(ticket.ticket_number)
        self.assertTrue(ticket.ticket_number.startswith("HQ-"))
        self.assertEqual(ticket.status, "open")
        self.assertIsNone(ticket.resolved_at)

    def test_ticket_auto_resolve_timestamp(self):
        """Test that resolved_at is auto-set when status changes to resolved."""
        ticket = SupportTicket.objects.create(
            business=self.business,
            title="Payment Failed",
            description="Payment processing error",
            category="payment",
            status="open",
        )

        # Resolve the ticket
        ticket.status = "resolved"
        ticket.save()

        self.assertIsNotNone(ticket.resolved_at)
        self.assertIsNone(ticket.closed_at)

        # Close the ticket
        ticket.status = "closed"
        ticket.save()

        self.assertIsNotNone(ticket.closed_at)


class BusinessNoteTestCase(TestCase):
    """Test BusinessNote model."""

    def setUp(self):
        """Set up test data."""
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.save()

        self.business = Business.objects.create(name="Test Business", slug="test-business", status="ACTIVE")

    def test_create_business_note(self):
        """Test creating a pinned note for a business."""
        note = BusinessNote.objects.create(
            business=self.business,
            author=self.hq_admin,
            title="Special Billing Arrangement",
            content="This business has a custom payment plan",
            is_pinned=True,
        )

        self.assertEqual(note.business, self.business)
        self.assertEqual(note.author, self.hq_admin)
        self.assertTrue(note.is_pinned)
        self.assertIsNotNone(note.created_at)


class TemplateRenderingTestCase(TestCase):
    """Test that HQ templates render without errors."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()

        self.business = Business.objects.create(name="Test Business", slug="test-business", status="ACTIVE")

        self.client.login(username="admin_hq", password="testpass123")

    def test_business_directory_renders(self):
        """Test that business directory template renders."""
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hq/business_directory.html")

    def test_business_command_center_renders(self):
        """Test that business command center template renders."""
        response = self.client.get(reverse("hq:business_command_center", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hq/business_command_center.html")

    def test_account_support_renders(self):
        """Test that account support template renders."""
        response = self.client.get(reverse("hq:account_support", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hq/account_support.html")


class ChartDataTestCase(TestCase):
    """Test that chart data is generated correctly."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()

        self.client.login(username="admin_hq", password="testpass123")

    def test_business_directory_has_chart_data(self):
        """Test that business directory context includes chart data."""
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("chart_data", response.context)
        self.assertIn("support_health_score", response.context)

    def test_chart_data_is_valid_json(self):
        """Test that chart data is valid JSON."""
        import json

        response = self.client.get(reverse("hq:business_directory"))
        chart_data = response.context.get("chart_data")

        if chart_data:
            try:
                parsed_data = json.loads(chart_data)
                self.assertIsInstance(parsed_data, dict)
            except json.JSONDecodeError:
                self.fail("Chart data is not valid JSON")


class HQRedirectAndActiveTabTestCase(TestCase):
    """Test HQ redirect loop fix and active_tab template variable."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()

        self.business = Business.objects.create(name="Test Business", slug="test-business", status="ACTIVE")

        self.client.login(username="admin_hq", password="testpass123")

    def test_hq_businesses_alias_returns_200_directly(self):
        """Test /hq/businesses/ returns 200 directly (no redirect to prevent loops)."""
        response = self.client.get(reverse("hq:businesses"))
        # Should return 200 directly (not redirect) to prevent redirect loops
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hq/business_directory.html")

    def test_hq_businesses_no_redirect_loop(self):
        """Test /hq/businesses/ does NOT cause infinite redirect loop."""
        # Follow the redirect and ensure we get 200 at the end
        response = self.client.get(reverse("hq:businesses"), follow=True)
        self.assertEqual(response.status_code, 200)
        # Should end up at business_directory
        self.assertTemplateUsed(response, "hq/business_directory.html")
        # Should have 0 redirects (direct view) or at most 1
        self.assertLessEqual(len(response.redirect_chain), 1)

    def test_hq_directory_returns_200_for_staff(self):
        """Test /hq/directory/ returns 200 for HQ staff."""
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hq/business_directory.html")

    def test_subscription_gate_does_not_block_hq_paths(self):
        """Test that SubscriptionGateMiddleware allows /hq/ paths."""
        # This test verifies middleware behavior
        # HQ staff should access HQ paths regardless of middleware
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("hq:business_command_center", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("hq:account_support", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)

    def test_hq_directory_renders_with_active_tab(self):
        """Test that business directory template has active_tab in context."""
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("active_tab", response.context)
        self.assertEqual(response.context["active_tab"], "directory")

    def test_hq_subscriptions_renders(self):
        """Test that HQ subscriptions page renders without errors."""
        response = self.client.get(reverse("hq:subscriptions"))
        self.assertEqual(response.status_code, 200)
        # Should have active_tab in context
        self.assertIn("active_tab", response.context)

    def test_hq_command_center_renders_with_active_tab(self):
        """Test that business command center has active_tab in context."""
        response = self.client.get(reverse("hq:business_command_center", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("active_tab", response.context)
        # Default tab is 'overview'
        self.assertEqual(response.context["active_tab"], "overview")

    def test_hq_account_support_renders_with_active_tab(self):
        """Test that account support page has active_tab in context."""
        response = self.client.get(reverse("hq:account_support", kwargs={"business_id": self.business.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("active_tab", response.context)
        self.assertEqual(response.context["active_tab"], "account_support")


class RedirectLoopRegressionTestCase(TestCase):
    """
    REGRESSION TESTS for /hq/businesses/ redirect loop bug.

    Previously: /hq/businesses/ would redirect to /hq/directory/, which could
    trigger middleware redirects back to /hq/businesses/, causing Chrome ERR_TOO_MANY_REDIRECTS.

    Now: /hq/businesses/ is a REAL VIEW that returns 200, with middleware bypasses.
    """

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create HQ admin (superuser)
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()

        # Create a test business for data to display
        self.business = Business.objects.create(
            name="Test Business", slug="test-business", created_by=self.hq_admin, status="ACTIVE"
        )

    def test_hq_businesses_returns_200_not_redirect(self):
        """
        CRITICAL: /hq/businesses/ must return 200 directly, not redirect.
        This is the PRIMARY fix for the redirect loop.
        """
        self.client.force_login(self.hq_admin)
        response = self.client.get("/hq/businesses/")

        # Must be 200, not 302
        self.assertEqual(
            response.status_code,
            200,
            f"Expected 200 but got {response.status_code}. " f"Location header: {response.get('Location', 'None')}",
        )

        # Should render the business directory template
        self.assertContains(response, "Business Directory")

    def test_hq_businesses_no_redirect_loop_with_follow(self):
        """
        Test that following redirects does not cause TooManyRedirects exception.
        Django test client raises TooManyRedirects after 20 redirects.
        """
        self.client.force_login(self.hq_admin)

        # This should NOT raise TooManyRedirects
        response = self.client.get("/hq/businesses/", follow=True)

        self.assertEqual(response.status_code, 200)

        # Should have ZERO redirects (or at most 1 if legacy alias redirects)
        self.assertLessEqual(len(response.redirect_chain), 1, f"Too many redirects: {response.redirect_chain}")

    def test_staff_user_no_active_business_can_access_hq(self):
        """
        Staff users without an active business should still access HQ pages.
        This tests the ActiveBusinessMiddleware bypass for staff/superusers.
        """
        # Clear any session data that might have business set
        self.client.force_login(self.hq_admin)
        session = self.client.session
        session.pop("active_business_id", None)
        session.pop("biz_id", None)
        session.save()

        # Should still return 200
        response = self.client.get("/hq/businesses/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Directory")

    def test_superuser_bypasses_tenant_middleware(self):
        """
        Superusers should bypass ActiveBusinessMiddleware entirely on HQ paths.
        Specifically tests that /hq/businesses/ never redirects to /tenants/choose/.
        """
        self.client.force_login(self.hq_admin)

        # Test the specific path we're fixing
        response = self.client.get("/hq/businesses/", follow=True)

        self.assertEqual(response.status_code, 200, f"/hq/businesses/ returned {response.status_code}")

        # Ensure we never redirected to /tenants/choose/
        for redirect_url, _ in response.redirect_chain:
            self.assertNotIn(
                "/tenants/choose", redirect_url, "/hq/businesses/ redirected to /tenants/choose/ which causes loops"
            )

        # Also test /hq/directory/ which is the canonical directory view
        response = self.client.get("/hq/directory/", follow=True)
        self.assertEqual(response.status_code, 200)
        for redirect_url, _ in response.redirect_chain:
            self.assertNotIn("/tenants/choose", redirect_url)

    def test_hq_businesses_named_route(self):
        """Test that the named route 'hq:businesses' works and returns 200."""
        self.client.force_login(self.hq_admin)
        response = self.client.get(reverse("hq:businesses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Directory")

    def test_prevent_hq_middleware_loop_guard(self):
        """
        Test that PreventHQFromClientUI never redirects when already on /hq/ paths.
        This is a loop guard test specifically for /hq/businesses/.
        """
        self.client.force_login(self.hq_admin)

        # /hq/businesses/ should never cause a redirect loop
        response = self.client.get("/hq/businesses/")

        # Should be 200 (not 302)
        self.assertEqual(response.status_code, 200, f"/hq/businesses/ returned {response.status_code} instead of 200")

        # Also test /hq/directory/ which should always return 200
        response = self.client.get("/hq/directory/")
        self.assertEqual(response.status_code, 200)


class HQTemplateDataContractTestCase(TestCase):
    """
    Test that HQ templates receive proper data contracts and handle missing data safely.
    Regression tests for template VariableDoesNotExist and RelatedObjectDoesNotExist errors.
    """

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create HQ admin (superuser)
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()

        # Create business WITHOUT subscription
        self.business_no_sub = Business.objects.create(
            name="Business Without Subscription", slug="biz-no-sub", created_by=self.hq_admin, status="ACTIVE"
        )

        # Create business WITH subscription
        self.business_with_sub = Business.objects.create(
            name="Business With Subscription", slug="biz-with-sub", created_by=self.hq_admin, status="ACTIVE"
        )

        # Create a subscription plan first (get_or_create to avoid unique constraint violations)
        from billing.models import SubscriptionPlan

        self.plan, _ = SubscriptionPlan.objects.get_or_create(
            code="starter_test",
            defaults={"name": "Starter Plan Test", "amount": 20000, "interval": "month", "is_active": True},
        )

        # Create subscription for second business
        from datetime import timedelta
        from django.utils import timezone

        self.subscription = BusinessSubscription.objects.create(
            business=self.business_with_sub,
            plan=self.plan,
            status="trial",
            trial_end=timezone.now() + timedelta(days=30),
            current_period_end=timezone.now() + timedelta(days=30),
        )

        self.client.force_login(self.hq_admin)

    def test_business_directory_renders_without_template_var_errors(self):
        """
        Test that business directory renders without VariableDoesNotExist errors.
        Ensures sub_state dict always has all required keys (days_remaining, plan_name, etc).
        """
        response = self.client.get(reverse("hq:business_directory"))

        # Should return 200, not crash
        self.assertEqual(response.status_code, 200, f"Business directory returned {response.status_code}, expected 200")

        # Check that context has businesses
        self.assertIn("businesses", response.context)

        # Ensure all businesses in context have sub_state with required keys
        for biz in response.context["businesses"]:
            self.assertTrue(hasattr(biz, "sub_state"), f"Business {biz.name} missing sub_state")

            # Check all required keys exist
            required_keys = ["status", "is_active", "days_remaining", "plan_name"]
            for key in required_keys:
                self.assertIn(key, biz.sub_state, f"Business {biz.name} sub_state missing key: {key}")

    def test_business_detail_handles_missing_subscription(self):
        """
        Test that business detail view handles businesses without subscriptions.
        Should not raise RelatedObjectDoesNotExist error.
        """
        # Test business WITHOUT subscription
        response = self.client.get(reverse("hq:business_detail", kwargs={"pk": self.business_no_sub.id}))

        # Should return 200, not crash
        self.assertEqual(
            response.status_code, 200, f"Business detail (no sub) returned {response.status_code}, expected 200"
        )

        # Context should have subscription key (even if None)
        self.assertIn("subscription", response.context)

        # Should be None for business without subscription
        self.assertIsNone(response.context["subscription"])

        # Test business WITH subscription
        response = self.client.get(reverse("hq:business_detail", kwargs={"pk": self.business_with_sub.id}))

        self.assertEqual(response.status_code, 200)
        self.assertIn("subscription", response.context)
        self.assertIsNotNone(response.context["subscription"])

    def test_hq_home_dashboard_renders_sqlite_safe(self):
        """
        Test that /hq/home/ dashboard renders without SQLite datetime UDF errors.
        Ensures TruncDate/TruncMonth operations don't crash on SQLite.
        """
        response = self.client.get(reverse("hq:home"))

        # Should return 200, not raise OperationalError
        self.assertEqual(response.status_code, 200, f"/hq/home/ returned {response.status_code}, expected 200")

        # Check that context has required chart data
        self.assertIn("monthly_sales_labels", response.context)
        self.assertIn("monthly_sales_data", response.context)

    def test_hq_agents_renders_successfully(self):
        """
        Test that /hq/agents/ renders without errors.
        Ensures agents list handles businesses with/without subscriptions safely.
        """
        # Create an agent for the business without subscription
        from tenants.models import Membership

        Membership.objects.create(business=self.business_no_sub, user=self.hq_admin, role="AGENT", status="ACTIVE")

        response = self.client.get(reverse("hq:agents"))

        # Should return 200, not crash
        self.assertEqual(response.status_code, 200, f"/hq/agents/ returned {response.status_code}, expected 200")

        # Check that context has rows
        self.assertIn("rows", response.context)
        self.assertIn("page_obj", response.context)

    def test_business_directory_clickable_rows(self):
        """
        Test that business directory template includes clickable rows.
        Ensures rows have proper onclick/href attributes.
        """
        response = self.client.get(reverse("hq:business_directory"))
        self.assertEqual(response.status_code, 200)

        # Check that response HTML contains clickable elements
        html = response.content.decode("utf-8")
        self.assertIn("business-row", html, "Missing business-row class")

        # Should have links to business detail
        self.assertIn("hq:business_detail", html.lower() or self.business_no_sub.name.lower() in html.lower())


class SQLiteDateTimeSafetyTestCase(TestCase):
    """
    Test that all datetime aggregations are SQLite-safe.
    Ensures no UDF exceptions are raised on SQLite.
    """

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create HQ admin
        self.hq_admin = User.objects.create_user(username="admin_hq", email="admin@hq.com", password="testpass123")
        self.hq_admin.is_staff = True
        self.hq_admin.is_superuser = True
        self.hq_admin.save()

        # Create a business and some test sales
        self.business = Business.objects.create(
            name="Test Business", slug="test-biz", created_by=self.hq_admin, status="ACTIVE"
        )

        self.client.force_login(self.hq_admin)

    def test_dashboard_monthly_aggregation_sqlite_safe(self):
        """Test that monthly sales aggregation doesn't crash on SQLite."""
        response = self.client.get(reverse("hq:home"))
        self.assertEqual(response.status_code, 200)

    def test_monthly_drill_down_api_sqlite_safe(self):
        """Test that monthly drill-down API doesn't crash on SQLite."""
        import datetime

        response = self.client.get(
            reverse("hq:monthly_drill_down_api"), {"year": datetime.date.today().year, "month": 1}
        )
        # Should return 200 with valid JSON
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("daily_sales", data)
        self.assertIn("daily_onboardings", data)
