"""
Website app tests — Phase 8.

Coverage:
- Website landing page renders (200)
- PWA manifest is served
- Light-mode content checks (no dark sections)
- Premium copy presence
- Logo img tag present
- Legal links present
- No childish / demo copy
- Trust & compliance section present
- Make Payment / Merchant Login present
"""

from django.test import TestCase, Client


class WebsiteSmokeTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_website_landing_renders(self):
        res = self.client.get("/site/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "TengaSale")

    def test_offline_page_renders(self):
        res = self.client.get("/offline/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "offline")


class WebsiteLightModeTest(TestCase):
    """Verify the public site stays in light mode throughout."""

    def setUp(self):
        self.client = Client()

    def _get(self):
        return self.client.get("/site/")

    def test_no_dark_background_inline_styles(self):
        """Landing page must not contain hardcoded dark background colours."""
        res = self._get()
        content = res.content.decode()
        forbidden = [
            "background: #080a10",
            "background:#080a10",
            "background: #0f172a",
            "background:#0f172a",
        ]
        for snippet in forbidden:
            self.assertNotIn(snippet, content, f"Found forbidden dark bg: {snippet!r}")

    def test_dark_section_class_not_used_on_compliance(self):
        """Trust & compliance section must not use site-section--dark."""
        res = self._get()
        content = res.content.decode()
        # The compliance section should NOT have the dark class
        self.assertNotIn('id="compliance" class="site-section site-section--dark"', content)
        self.assertNotIn("compliance-section site-section--dark", content)

    def test_compliance_section_light_class(self):
        """Trust & compliance section must use the light site-section--light class."""
        res = self._get()
        content = res.content.decode()
        self.assertIn("site-section--light", content, "Compliance section must use site-section--light")


class WebsiteCopyTest(TestCase):
    """Verify premium, professional copy is present and childish copy is absent."""

    def setUp(self):
        self.client = Client()

    def _get(self):
        return self.client.get("/site/")

    def test_no_pilot_ready(self):
        res = self._get()
        self.assertNotContains(res, "pilot-ready")

    def test_no_integration_ready_marketing(self):
        """'integration-ready' must not appear as a marketing chip/badge."""
        res = self._get()
        content = res.content.decode()
        # Allow "integration" in context, but not as a standalone fluff badge
        self.assertNotIn(">integration-ready<", content)
        self.assertNotIn("integration-ready</span>", content)

    def test_structured_repayment_copy(self):
        res = self._get()
        self.assertContains(res, "structured")

    def test_contains_contract_language(self):
        res = self._get()
        self.assertContains(res, "contract")

    def test_hero_realistic_amounts(self):
        """Hero must not use the old toy amount MWK 33,000."""
        res = self._get()
        self.assertNotContains(res, "MWK 33,000")

    def test_hero_contains_realistic_amount(self):
        """Hero should contain a realistic phone financing value."""
        res = self._get()
        content = res.content.decode()
        self.assertTrue(
            "900,000" in content or "62,500" in content or "540,000" in content,
            "Hero should contain realistic MWK phone-financing values",
        )


class WebsiteNavigationTest(TestCase):
    """Verify key CTAs and navigation elements are present."""

    def setUp(self):
        self.client = Client()

    def _get(self):
        return self.client.get("/site/")

    def test_make_payment_present(self):
        res = self._get()
        self.assertContains(res, "Make Payment")

    def test_merchant_login_present(self):
        res = self._get()
        self.assertContains(res, "Merchant Login")

    def test_logo_img_tag_present(self):
        """Header must contain an img tag for the TengaSale logo."""
        res = self._get()
        content = res.content.decode()
        self.assertIn("site-logo-img", content)
        self.assertIn("<img", content)

    def test_how_it_works_anchor(self):
        res = self._get()
        self.assertContains(res, "how-it-works")

    def test_merchants_anchor(self):
        res = self._get()
        self.assertContains(res, "for-merchants")

    def test_payments_nav_link(self):
        res = self._get()
        self.assertContains(res, "payment-channels")


class WebsiteTrustSectionTest(TestCase):
    """Verify trust & compliance section content."""

    def setUp(self):
        self.client = Client()

    def _get(self):
        return self.client.get("/site/")

    def test_trust_compliance_heading(self):
        res = self._get()
        self.assertContains(res, "Trust, compliance")

    def test_kyc_verification_present(self):
        res = self._get()
        self.assertContains(res, "KYC verification")

    def test_contract_records_present(self):
        res = self._get()
        self.assertContains(res, "Contract records")

    def test_audit_logs_present(self):
        res = self._get()
        self.assertContains(res, "Audit logs")

    def test_merchant_controls_present(self):
        res = self._get()
        self.assertContains(res, "Merchant controls")


class WebsiteFooterLegalTest(TestCase):
    """Verify footer legal links and light-mode footer."""

    def setUp(self):
        self.client = Client()

    def _get(self):
        return self.client.get("/site/")

    def test_terms_of_service_link(self):
        res = self._get()
        self.assertContains(res, "Terms of Service")

    def test_privacy_policy_link(self):
        res = self._get()
        self.assertContains(res, "Privacy Policy")

    def test_payment_terms_link(self):
        res = self._get()
        self.assertContains(res, "Payment Terms")

    def test_merchant_terms_link(self):
        res = self._get()
        self.assertContains(res, "Merchant Terms")

    def test_support_link(self):
        res = self._get()
        self.assertContains(res, "Help")

    def test_footer_not_dark(self):
        """Footer must not use the old dark #0f1117 background class."""
        res = self._get()
        content = res.content.decode()
        # Dark footer background colour must not appear inline in footer
        self.assertNotIn('background: #0f1117', content)
        self.assertNotIn('background:#0f1117', content)


class WebsiteLegalPagesTest(TestCase):
    """Verify all legal sub-pages render correctly."""

    def setUp(self):
        self.client = Client()

    def test_terms_page_renders(self):
        res = self.client.get("/site/terms/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Terms of Service")

    def test_privacy_page_renders(self):
        res = self.client.get("/site/privacy/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Privacy Policy")

    def test_payment_terms_page_renders(self):
        res = self.client.get("/site/payment-terms/")
        self.assertEqual(res.status_code, 200)

    def test_merchant_terms_page_renders(self):
        res = self.client.get("/site/merchant-terms/")
        self.assertEqual(res.status_code, 200)
