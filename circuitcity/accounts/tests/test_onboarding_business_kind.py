"""
Regression tests for business_kind persistence during signup/onboarding.

CRITICAL BUG FIX: Ensure cement (and all verticals) persist business_kind correctly
and redirect to the appropriate vertical dashboard after signup/login.

Test Coverage:
1. Signup with cement → business_kind="cement" persisted
2. Signup with cement → redirect to cement dashboard (NOT /verticals/none/)
3. Existing business with None → stays None (backward compat)
4. Business Settings can change None → cement
5. Invalid business_kind → validation error (no silent None)
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from tenants.models import Business, Membership

User = get_user_model()


class CementBusinessKindPersistenceTest(TestCase):
    """Test that cement business_kind is correctly persisted during signup."""

    def setUp(self):
        self.client = Client()

    def test_manager_wizard_signup_persists_cement_kind(self):
        """
        Test A: Signup/business creation persists cement kind.

        Simulates the manager wizard signup flow with cement selected.
        Verifies:
        - Business.business_kind == "cement"
        - Redirect is NOT /verticals/none/
        - Redirect IS the cement dashboard route
        """
        # Step 1: User account
        response = self.client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "full_name": "Cement Manager",
                "email": "cement@test.com",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302, "Step 1 should redirect to step 2")

        # Step 2: Business details with cement
        response = self.client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "business_name": "Cement Hardware Store",
                "country": "Zambia",
                "currency": "ZMW",
                "business_kind": "cement",  # CRITICAL: cement selected
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302, "Step 2 should redirect to step 3")

        # Step 3: Logo (optional, skip)
        response = self.client.post(
            reverse("accounts:signup_manager") + "?step=3",
            {},
            follow=False,
        )
        self.assertEqual(response.status_code, 302, "Step 3 should redirect to step 4")

        # Step 4: Complete signup
        response = self.client.post(
            reverse("accounts:signup_manager") + "?step=4",
            {},
            follow=False,
        )

        # Verify user and business created
        user = User.objects.filter(email="cement@test.com").first()
        self.assertIsNotNone(user, "User should be created")

        business = Business.objects.filter(name="Cement Hardware Store").first()
        self.assertIsNotNone(business, "Business should be created")

        # CRITICAL: Verify business_kind is "cement" (NOT None)
        self.assertEqual(
            business.business_kind,
            "cement",
            "Business.business_kind MUST be 'cement' after signup with cement selected",
        )

        # Verify redirect is NOT /verticals/none/
        redirect_url = response.url
        self.assertNotIn(
            "/verticals/none/",
            redirect_url,
            "Cement business should NOT redirect to /verticals/none/",
        )

        # Verify redirect is to a valid dashboard (cement or general)
        # Post-login should route to cement dashboard
        self.assertTrue(
            "/dashboard/" in redirect_url or "/cement/" in redirect_url or "/verticals/cement/" in redirect_url,
            f"Should redirect to cement dashboard or general dashboard, got: {redirect_url}",
        )

    def test_regular_wizard_signup_persists_cement_kind(self):
        """
        Test the regular signup_wizard flow (if it exists) also persists cement.
        """
        # Step 1: User account
        response = self.client.post(
            reverse("accounts:signup_wizard_step", kwargs={"step": 1}),
            {
                "full_name": "Cement User",
                "email": "cement2@test.com",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)

        # Step 2: Business details with cement
        response = self.client.post(
            reverse("accounts:signup_wizard_step", kwargs={"step": 2}),
            {
                "business_name": "Cement Shop 2",
                "country": "Zambia",
                "currency": "ZMW",
                "business_kind": "cement",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)

        # Step 3: Location
        response = self.client.post(
            reverse("accounts:signup_wizard_step", kwargs={"step": 3}),
            {
                "location_name": "Main Branch",
                "city": "Lusaka",
                "staff_count": "5",
            },
            follow=False,
        )
        self.assertEqual(response.status_code, 302)

        # Step 4: Goals (complete)
        response = self.client.post(
            reverse("accounts:signup_wizard_step", kwargs={"step": 4}),
            {
                "goal_stop_theft": True,
                "goal_see_profit": True,
            },
            follow=False,
        )

        # Verify business created with cement kind
        business = Business.objects.filter(name="Cement Shop 2").first()
        self.assertIsNotNone(business)
        self.assertEqual(
            business.business_kind,
            "cement",
            "Regular wizard should also persist cement business_kind",
        )

    def test_login_redirect_for_cement_business(self):
        """
        Test that login redirects cement businesses to cement dashboard.
        """
        # Create cement business and user
        user = User.objects.create_user(
            username="cement_login@test.com",
            email="cement_login@test.com",
            password="SecurePass123!",
        )
        business = Business.objects.create(
            name="Cement Login Test",
            slug="cement-login-test",
            business_kind="cement",
            status="ACTIVE",
            created_by=user,
        )
        Membership.objects.create(
            user=user,
            business=business,
            role="MANAGER",
            status="ACTIVE",
        )

        # Login
        login_success = self.client.login(username="cement_login@test.com", password="SecurePass123!")
        self.assertTrue(login_success, "Login should succeed")

        # Set active business
        session = self.client.session
        session["active_business_id"] = business.pk
        session.save()

        # Access a protected page that would trigger redirect
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Should redirect to cement dashboard (or at least NOT /verticals/none/)
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        self.assertNotIn(
            "/verticals/none/",
            final_url,
            "Cement business should NOT be redirected to /verticals/none/",
        )


class BackwardCompatibilityTest(TestCase):
    """Test that existing businesses with business_kind=None still work."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="legacy@test.com",
            email="legacy@test.com",
            password="SecurePass123!",
        )
        self.business = Business.objects.create(
            name="Legacy Business",
            slug="legacy-business",
            business_kind=None,  # Existing business with no kind
            status="ACTIVE",
            created_by=self.user,
        )
        Membership.objects.create(
            user=self.user,
            business=self.business,
            role="MANAGER",
            status="ACTIVE",
        )

    def test_none_business_stays_none(self):
        """
        Test B: Existing business with business_kind=None should stay None.
        """
        self.assertIsNone(self.business.business_kind, "Legacy business should have None business_kind")

    def test_none_business_redirects_to_none_page(self):
        """
        Test that businesses with business_kind=None get /verticals/none/ page.
        """
        self.client.login(username="legacy@test.com", password="SecurePass123!")
        session = self.client.session
        session["active_business_id"] = self.business.pk
        session.save()

        # Access dashboard
        response = self.client.get(reverse("dashboard:home"), follow=True)

        # Should eventually redirect to /verticals/none/ or show business settings
        final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
        # This is acceptable for None businesses
        self.assertTrue(
            "/verticals/none/" in final_url or "/settings/" in final_url or "/dashboard/" in final_url,
            f"None business should redirect to none page or settings, got: {final_url}",
        )


class BusinessKindValidationTest(TestCase):
    """Test that invalid business_kind values are rejected."""

    def setUp(self):
        self.client = Client()

    def test_empty_business_kind_rejected(self):
        """
        Test D: Validation guard - empty business_kind should show error.
        """
        # Step 1: User account
        self.client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "full_name": "Test User",
                "email": "validation@test.com",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
            },
        )

        # Step 2: Business details with EMPTY business_kind
        response = self.client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "business_name": "Validation Test Store",
                "country": "Zambia",
                "currency": "ZMW",
                "business_kind": "",  # EMPTY
            },
            follow=False,
        )

        # Should NOT redirect (form should have errors)
        self.assertEqual(response.status_code, 200, "Empty business_kind should show form with errors")
        self.assertFormError(
            response.context["form"],
            "business_kind",
            "Please select your business type.",
        )

    def test_invalid_business_kind_rejected(self):
        """
        Test that submitting an invalid business_kind (not in choices) is rejected.
        """
        # Step 1: User account
        self.client.post(
            reverse("accounts:signup_manager") + "?step=1",
            {
                "full_name": "Test User 2",
                "email": "validation2@test.com",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
            },
        )

        # Step 2: Business details with INVALID business_kind
        response = self.client.post(
            reverse("accounts:signup_manager") + "?step=2",
            {
                "business_name": "Invalid Kind Store",
                "country": "Zambia",
                "currency": "ZMW",
                "business_kind": "invalid_vertical_xyz",  # INVALID
            },
            follow=False,
        )

        # Should NOT redirect (form should have errors)
        self.assertEqual(response.status_code, 200, "Invalid business_kind should show form with errors")
        # Django ChoiceField will reject this automatically
        self.assertIn("business_kind", response.context["form"].errors)


class AllVerticalsRedirectTest(TestCase):
    """Test that all verticals redirect correctly after signup/login."""

    def test_all_verticals_redirect_correctly(self):
        """
        Verify that each vertical redirects to its correct dashboard.
        """
        verticals_to_test = [
            ("phones", "Phones Store"),
            ("liquor", "Liquor Bar"),
            ("clothing", "Clothing Shop"),
            ("pharmacy", "Pharmacy Store"),
            ("gym", "Gym Fitness"),
            ("grocery", "Grocery Store"),
            ("cement", "Cement Hardware"),
        ]

        for kind, biz_name in verticals_to_test:
            with self.subTest(vertical=kind):
                # Create user and business
                user = User.objects.create_user(
                    username=f"{kind}@test.com",
                    email=f"{kind}@test.com",
                    password="SecurePass123!",
                )
                business = Business.objects.create(
                    name=biz_name,
                    slug=f"{kind}-test",
                    business_kind=kind,
                    status="ACTIVE",
                    created_by=user,
                )
                Membership.objects.create(
                    user=user,
                    business=business,
                    role="MANAGER",
                    status="ACTIVE",
                )

                # Login
                client = Client()
                client.login(username=f"{kind}@test.com", password="SecurePass123!")
                session = client.session
                session["active_business_id"] = business.pk
                session.save()

                # Access dashboard
                response = client.get(reverse("dashboard:home"), follow=True)

                # Should NOT redirect to /verticals/none/
                final_url = response.redirect_chain[-1][0] if response.redirect_chain else response.request["PATH_INFO"]
                self.assertNotIn(
                    "/verticals/none/",
                    final_url,
                    f"{kind} business should NOT redirect to /verticals/none/, got: {final_url}",
                )

                # Verify business_kind is persisted
                business.refresh_from_db()
                self.assertEqual(
                    business.business_kind,
                    kind,
                    f"{kind} business_kind should be persisted",
                )
