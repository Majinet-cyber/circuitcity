"""
Regression tests for public pages content consistency.

These tests prevent content issues from returning:
1. Metrics consistency - no conflicting numbers on the same page
2. Terminology consistency - pricing uses "records" and "team seats"
3. Required sections exist on each page
4. SEO elements are present

NON-NEGOTIABLE: These tests must pass before deployment.
"""
import re
import pytest
from django.test import TestCase, Client
from django.urls import reverse


class HomePageContentTests(TestCase):
    """Tests for homepage content consistency and required sections."""

    def setUp(self):
        self.client = Client()

    def test_homepage_renders_200(self):
        """Homepage must render successfully."""
        response = self.client.get(reverse("staticpages:home"))
        self.assertEqual(response.status_code, 200)

    def test_homepage_contains_hero_headline(self):
        """Homepage must contain the hero headline."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        # Check for the multi-vertical aware headline
        self.assertTrue(
            "shop, farm, or gym" in content.lower() or "run your" in content.lower(),
            "Hero headline should mention multiple business types"
        )

    def test_homepage_contains_how_it_works(self):
        """Homepage must contain How It Works section."""
        response = self.client.get(reverse("staticpages:home"))
        self.assertContains(response, "How It Works")
        self.assertContains(response, "how-it-works")

    def test_homepage_contains_features_section(self):
        """Homepage must contain a core features section with inventory/sales content."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        # The features section should showcase core product capabilities
        self.assertTrue(
            "features" in content.lower() or "Core Platform" in content or "inventory" in content.lower(),
            "Homepage should have a features/capabilities section"
        )

    def test_homepage_contains_product_capabilities(self):
        """Homepage must present key product capabilities (inventory, sales, profit)."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8").lower()
        # Core capabilities must be represented
        capabilities = ["inventory", "sales", "profit"]
        found = sum(1 for cap in capabilities if cap in content)
        self.assertGreaterEqual(
            found, 2,
            f"Homepage should cover core product capabilities. Found: {found}/3"
        )

    def test_homepage_no_zero_plus_with_join_x(self):
        """
        CRITICAL: Homepage must not show "0+ Active" while also showing "Join X+ businesses".
        This is the biggest trust leak - metrics must be consistent.
        """
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        
        # Check for "0+ Active" patterns (the problematic counter display)
        has_zero_counter = bool(re.search(r'data-target="0"', content))
        
        # Check for "Join X+ businesses" where X > 0
        join_pattern = re.search(r'Join\s+(\d+)\+?\s+businesses', content, re.IGNORECASE)
        has_join_claim = join_pattern is not None and int(join_pattern.group(1)) > 0
        
        # These two should not coexist - either show real metrics or hide counters
        if has_zero_counter and has_join_claim:
            self.fail(
                "Metrics inconsistency: Page shows 0+ counter while also claiming "
                f"'Join {join_pattern.group(1)}+ businesses'. "
                "Either hide counters or use consistent numbers."
            )

    def test_homepage_vertical_awareness(self):
        """Homepage should mention multiple verticals (shop, farm, gym, etc.)."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8").lower()
        
        # Should mention at least 2 of these verticals
        verticals = ["shop", "farm", "gym", "liquor", "cement"]
        mentioned = sum(1 for v in verticals if v in content)
        
        self.assertGreaterEqual(
            mentioned, 2,
            f"Homepage should mention at least 2 business verticals. Found: {mentioned}"
        )


class MetricsConsistencyTests(TestCase):
    """Tests to ensure metrics are consistent across all public pages."""

    def setUp(self):
        self.client = Client()

    def test_metrics_use_centralized_source(self):
        """Verify that PUBLIC_SITE_METRICS exists in settings."""
        from django.conf import settings
        
        self.assertTrue(
            hasattr(settings, "PUBLIC_SITE_METRICS"),
            "PUBLIC_SITE_METRICS must be defined in settings as SSOT"
        )
        
        metrics = settings.PUBLIC_SITE_METRICS
        self.assertIn("active_businesses", metrics)
        self.assertIn("registered_agents", metrics)
        self.assertIn("show_counters", metrics)
        self.assertIn("min_threshold", metrics)

    def test_context_processor_provides_public_metrics(self):
        """Verify context processor provides PUBLIC_METRICS to templates."""
        from django.test import RequestFactory
        from cc.context_processors import marketing_constants
        
        factory = RequestFactory()
        request = factory.get("/")
        
        context = marketing_constants(request)
        
        self.assertIn("PUBLIC_METRICS", context)
        self.assertIn("active_businesses", context["PUBLIC_METRICS"])
        self.assertIn("show_counters", context["PUBLIC_METRICS"])


class PricingPageContentTests(TestCase):
    """Tests for pricing page terminology and content."""

    def setUp(self):
        self.client = Client()

    def test_pricing_page_renders_200(self):
        """Pricing page must render successfully."""
        response = self.client.get(reverse("staticpages:pricing"))
        self.assertEqual(response.status_code, 200)

    def test_pricing_uses_records_terminology(self):
        """Pricing page should use 'records' instead of 'stock items'."""
        response = self.client.get(reverse("staticpages:pricing"))
        content = response.content.decode("utf-8")
        
        # Should contain "records"
        self.assertIn("records", content.lower())

    def test_pricing_uses_team_seats_terminology(self):
        """Pricing page should use 'team seats' instead of just 'agents'."""
        response = self.client.get(reverse("staticpages:pricing"))
        content = response.content.decode("utf-8")
        
        # Should contain "team seats" or "team"
        self.assertTrue(
            "team seats" in content.lower() or "team" in content.lower(),
            "Pricing should use 'team seats' terminology"
        )

    def test_pricing_has_vertical_explanation(self):
        """Pricing page should explain what 'records' and 'team seats' mean."""
        response = self.client.get(reverse("staticpages:pricing"))
        content = response.content.decode("utf-8").lower()
        
        # Should have some explanation of terminology
        self.assertTrue(
            "products" in content or "members" in content or "crops" in content,
            "Pricing should explain what 'records' means for different verticals"
        )


class AboutPageContentTests(TestCase):
    """Tests for about page content and trust elements."""

    def setUp(self):
        self.client = Client()

    def test_about_page_renders_200(self):
        """About page must render successfully."""
        response = self.client.get(reverse("staticpages:about"))
        self.assertEqual(response.status_code, 200)

    def test_about_page_contains_support_section(self):
        """About page must contain Support section."""
        response = self.client.get(reverse("staticpages:about"))
        content = response.content.decode("utf-8")
        
        # Check for support-related content
        self.assertTrue(
            "support" in content.lower() and (
                "whatsapp" in content.lower() or 
                "email" in content.lower() or
                "onboarding" in content.lower()
            ),
            "About page should have a Support section with contact info"
        )

    def test_about_page_contains_trust_section(self):
        """About page must contain 'Why businesses trust Emajinet' section."""
        response = self.client.get(reverse("staticpages:about"))
        content = response.content.decode("utf-8")
        
        # Check for trust-related content
        trust_keywords = ["trust", "permissions", "audit", "roles", "security"]
        found = sum(1 for kw in trust_keywords if kw in content.lower())
        
        self.assertGreaterEqual(
            found, 2,
            f"About page should have trust elements. Found {found} keywords."
        )

    def test_about_page_no_engineering_terms(self):
        """About page should NOT mention internal engineering terms."""
        response = self.client.get(reverse("staticpages:about"))
        content = response.content.decode("utf-8").lower()
        
        forbidden_terms = ["ci/cd", "regression", "monorepo", "pytest", "unittest"]
        
        for term in forbidden_terms:
            self.assertNotIn(
                term, content,
                f"About page should not mention '{term}' - this is internal engineering"
            )


class SEOTests(TestCase):
    """Tests for SEO elements on public pages."""

    def setUp(self):
        self.client = Client()

    def test_homepage_has_meta_description(self):
        """Homepage must have a meta description."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        
        self.assertIn('name="description"', content)
        self.assertIn("malawi", content.lower())

    def test_homepage_has_og_tags(self):
        """Homepage must have Open Graph tags."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        
        self.assertIn('property="og:title"', content)
        self.assertIn('property="og:description"', content)
        self.assertIn('property="og:image"', content)

    def test_homepage_has_canonical_url(self):
        """Homepage must have a canonical URL."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        
        self.assertIn('rel="canonical"', content)
        self.assertIn("emajinet.africa", content)

    def test_pricing_page_has_seo_elements(self):
        """Pricing page must have SEO elements."""
        response = self.client.get(reverse("staticpages:pricing"))
        content = response.content.decode("utf-8")
        
        self.assertIn('name="description"', content)
        self.assertIn('rel="canonical"', content)

    def test_about_page_has_seo_elements(self):
        """About page must have SEO elements."""
        response = self.client.get(reverse("staticpages:about"))
        content = response.content.decode("utf-8")
        
        self.assertIn('name="description"', content)
        self.assertIn('rel="canonical"', content)


class HeadingHierarchyTests(TestCase):
    """Tests for proper heading hierarchy (accessibility)."""

    def setUp(self):
        self.client = Client()

    def test_homepage_has_h1(self):
        """Homepage must have exactly one H1 tag."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        
        h1_count = content.count("<h1")
        self.assertEqual(h1_count, 1, f"Homepage should have exactly 1 H1 tag, found {h1_count}")

    def test_homepage_has_h2_sections(self):
        """Homepage must have H2 tags for main sections."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        
        h2_count = content.count("<h2")
        self.assertGreaterEqual(h2_count, 3, "Homepage should have at least 3 H2 section headings")


@pytest.mark.django_db
class PublicPagesRegressionTests(TestCase):
    """Integration tests to ensure all public pages work together."""

    def test_all_public_pages_accessible(self):
        """All public pages should be accessible (200 or redirect)."""
        public_urls = [
            reverse("staticpages:home"),
            reverse("staticpages:about"),
            reverse("staticpages:pricing"),
            reverse("staticpages:contact"),
            reverse("staticpages:terms"),
            reverse("staticpages:privacy"),
        ]
        
        for url in public_urls:
            response = self.client.get(url)
            self.assertIn(
                response.status_code, [200, 301, 302],
                f"{url} should be accessible, got {response.status_code}"
            )

    def test_no_broken_internal_links(self):
        """Homepage links to other public pages should work."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        
        # Check that links to pricing and about are present
        self.assertIn("/landing/pricing/", content)
        self.assertIn("/landing/about/", content)

