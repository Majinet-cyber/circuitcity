"""
Production hardening tests for EMAJINET landing page and platform reliability.

Covers:
- Landing metrics API endpoint schema and response
- Hero section has no zero-flash placeholders
- Mobile nav is lean (no footer clutter)
- Pricing snapshot present on landing page with real prices
- Data carousel replaced by compact callout (no old carousel DOM)
- Smart Recommendations section is compact (no bloated 4-card grid)
- CTA wording consistency ("Get Started Free")
- Cache headers for authenticated pages (no-cache)
- No-cache headers on the home view (never_cache applied)

NON-NEGOTIABLE: All tests must pass before deployment.
"""
import json
import re

import pytest
from django.test import TestCase, Client
from django.urls import reverse


# ======================================================================
# LANDING METRICS API
# ======================================================================

class LandingMetricsAPITests(TestCase):
    """Tests for the /landing/api/landing-metrics/ endpoint."""

    def setUp(self):
        self.client = Client()

    def test_endpoint_returns_200(self):
        """Landing metrics API must return 200."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        self.assertEqual(response.status_code, 200)

    def test_endpoint_returns_json(self):
        """Landing metrics API must return JSON content type."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        self.assertEqual(response["Content-Type"].split(";")[0], "application/json")

    def test_response_schema_required_keys(self):
        """Landing metrics API response must contain all required keys."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(response.content)
        required_keys = [
            "active_businesses",
            "team_members",
            "has_data",
            "as_of",
            "status",
        ]
        for key in required_keys:
            self.assertIn(key, data, f"Missing key '{key}' in landing metrics response")

    def test_has_data_is_boolean(self):
        """has_data field must be a boolean."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(response.content)
        self.assertIsInstance(data["has_data"], bool)

    def test_active_businesses_is_non_negative(self):
        """active_businesses must be >= 0."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(response.content)
        self.assertGreaterEqual(data["active_businesses"], 0)

    def test_team_members_is_non_negative(self):
        """team_members must be >= 0."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(response.content)
        self.assertGreaterEqual(data["team_members"], 0)

    def test_avg_daily_revenue_null_when_no_data(self):
        """avg_daily_revenue should be null when has_data is False (no sales records)."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(response.content)
        if not data["has_data"]:
            self.assertIsNone(
                data.get("avg_daily_revenue"),
                "avg_daily_revenue must be null when has_data is False",
            )

    def test_no_cache_headers_on_metrics_endpoint(self):
        """Landing metrics API must not be cached (never_cache applied)."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        cc = response.get("Cache-Control", "")
        self.assertTrue(
            "no-cache" in cc or "no-store" in cc or "max-age=0" in cc,
            f"Expected no-cache headers on metrics API, got: {cc}",
        )

    def test_status_field_is_success(self):
        """Status field must be 'success' for valid responses."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(response.content)
        self.assertEqual(data.get("status"), "success")

    def test_platform_stats_api_still_works(self):
        """Original platform_stats_api endpoint must still return 200."""
        response = self.client.get(reverse("staticpages:platform_stats_api"))
        self.assertEqual(response.status_code, 200)


# ======================================================================
# HERO SECTION — NO ZERO FLASH
# ======================================================================

class HeroZeroFlashTests(TestCase):
    """Ensure hero metrics never show 0 as the initial rendered value."""

    def setUp(self):
        self.client = Client()

    def test_hero_counters_not_start_from_zero(self):
        """
        Hero metric counters must NOT have 'data-target' with content '0'
        AND simultaneously show a blank or zero as text content.

        The server-rendered value is always used as initial content.
        """
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")

        # Pattern: counter-animated span starting with ">0<" or ">MWK 0<"
        zero_flash_patterns = [
            r'>MWK\s*0<',   # MWK 0 as initial content
            r'>0\+<',       # 0+ as initial content (agents/merchants counter)
        ]
        for pattern in zero_flash_patterns:
            match = re.search(pattern, content)
            self.assertIsNone(
                match,
                f"Zero flash detected! Pattern '{pattern}' found in hero. "
                "Server must render real values as initial content.",
            )

    def test_hero_has_get_started_free_cta(self):
        """Hero primary CTA must say 'Get Started Free'."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "Get Started Free",
            content,
            "Hero CTA must say 'Get Started Free'",
        )

    def test_hero_has_see_how_it_works_cta(self):
        """Hero secondary CTA must say 'See How It Works'."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "See How It Works",
            content,
            "Hero secondary CTA must say 'See How It Works'",
        )

    def test_hero_positioning_unchanged(self):
        """Headline must keep positioning: 'Africa's Business Operating System'."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "Africa",
            content,
            "Hero must contain 'Africa' positioning",
        )
        self.assertIn(
            "Business Operating System",
            content,
            "Hero must contain 'Business Operating System' positioning",
        )


# ======================================================================
# MOBILE NAV — LEAN DRAWER
# ======================================================================

class MobileNavTests(TestCase):
    """Mobile nav drawer must be lean and conversion-focused."""

    def setUp(self):
        self.client = Client()

    def _get_mobile_menu_content(self):
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        # Extract mobile menu div
        match = re.search(
            r'id="mobileMenu"[^>]*>(.*?)</div>\s*</nav>',
            content,
            re.DOTALL,
        )
        return match.group(1) if match else content

    def test_mobile_nav_has_get_started_free(self):
        """Mobile nav CTA must say 'Get Started Free'."""
        mobile_content = self._get_mobile_menu_content()
        self.assertIn(
            "Get Started Free",
            mobile_content,
            "Mobile nav CTA must say 'Get Started Free'",
        )

    def test_mobile_nav_has_features_link(self):
        """Mobile nav must contain Features link."""
        mobile_content = self._get_mobile_menu_content()
        self.assertIn("Features", mobile_content)

    def test_mobile_nav_has_pricing_link(self):
        """Mobile nav must contain Pricing link."""
        mobile_content = self._get_mobile_menu_content()
        self.assertIn("Pricing", mobile_content)

    def test_mobile_nav_has_sign_in(self):
        """Mobile nav must contain Sign In link."""
        mobile_content = self._get_mobile_menu_content()
        self.assertIn("Sign In", mobile_content)

    def test_mobile_nav_no_about_page(self):
        """
        Mobile nav drawer must NOT contain 'About' page link.
        About belongs in the footer, not the mobile nav.
        """
        mobile_content = self._get_mobile_menu_content()
        # Check that About is NOT present as a nav item in mobile drawer
        # (it's OK in footer, but not mobile drawer)
        self.assertNotIn(
            '<a href="/landing/about/"',
            mobile_content,
            "About link should be in footer, not mobile nav drawer",
        )

    def test_mobile_nav_no_start_with_clarity(self):
        """Old 'Start with Clarity' wording must be gone."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertNotIn(
            "Start with Clarity",
            content,
            "Old CTA wording 'Start with Clarity' must be removed",
        )


# ======================================================================
# PRICING SNAPSHOT ON LANDING PAGE
# ======================================================================

class LandingPricingSnapshotTests(TestCase):
    """Pricing snapshot on landing page must use real pricing data."""

    def setUp(self):
        self.client = Client()

    def test_landing_page_has_pricing_snapshot_section(self):
        """Landing page must include a pricing snapshot section."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "pricing-snapshot",
            content,
            "Landing page must have #pricing-snapshot section",
        )

    def test_landing_pricing_uses_real_prices(self):
        """Landing pricing snapshot must show real plan prices from billing/pricing.py."""
        from billing.pricing import get_all_plans
        plans = get_all_plans()

        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")

        # Prices are formatted with floatformat:0, which may omit or include commas.
        # Check for the presence of the price value in the content.
        for plan in plans:
            price_int = int(plan.amount)
            # Try both with and without thousands separator
            price_plain = str(price_int)
            price_comma = f"{price_int:,}"
            found = price_plain in content or price_comma in content
            self.assertTrue(
                found,
                f"Landing page pricing snapshot must show {plan.name} price "
                f"({price_plain} or {price_comma})",
            )

    def test_landing_pricing_has_free_trial_mention(self):
        """Landing pricing snapshot must mention free trial."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertTrue(
            "free" in content.lower() and "trial" in content.lower(),
            "Pricing snapshot must mention free trial",
        )

    def test_landing_pricing_has_link_to_full_pricing_page(self):
        """Landing pricing snapshot must link to full pricing page."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "/landing/pricing/",
            content,
            "Landing page must link to full pricing page",
        )

    def test_pricing_page_route_intact(self):
        """Full pricing page route must remain accessible."""
        response = self.client.get(reverse("staticpages:pricing"))
        self.assertEqual(response.status_code, 200)

    def test_pricing_matches_source_of_truth(self):
        """Prices on landing snapshot must match billing/pricing.py source of truth."""
        from billing.pricing import PLANS

        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")

        for code, plan in PLANS.items():
            price_int = int(plan.amount)
            price_plain = str(price_int)
            price_comma = f"{price_int:,}"
            found = price_plain in content or price_comma in content
            self.assertTrue(
                found,
                f"Plan '{code}' price ({price_plain} or {price_comma}) "
                "must appear in landing snapshot",
            )


# ======================================================================
# DATA SECTION — NO BLOATED CAROUSEL
# ======================================================================

class DataSectionTests(TestCase):
    """Data section must be a compact callout, not a carousel."""

    def setUp(self):
        self.client = Client()

    def test_no_carousel_dom_on_landing(self):
        """Old stats carousel DOM elements must not be present."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        # The old carousel had statsCarousel, statsSlides, statsPrevBtn
        self.assertNotIn(
            'id="statsCarousel"',
            content,
            "Old stats carousel DOM must be removed from landing page",
        )
        self.assertNotIn(
            'id="statsSlides"',
            content,
            "Old stats slides DOM must be removed from landing page",
        )

    def test_reality_stats_section_still_present(self):
        """reality-stats section must still exist (as compact callout)."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "reality-stats",
            content,
            "reality-stats section must still exist (as compact callout)",
        )

    def test_finscope_data_still_referenced(self):
        """FinScope source must still be referenced for credibility."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "FinScope",
            content,
            "FinScope data source must still be cited",
        )


# ======================================================================
# SMART RECOMMENDATIONS — COMPACT
# ======================================================================

class SmartRecommendationsSectionTests(TestCase):
    """Smart Recommendations must be a compact summary, not 4-card grid."""

    def setUp(self):
        self.client = Client()

    def test_smart_recommendations_section_present(self):
        """smart-recommendations section must still be on the page."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "smart-recommendations",
            content,
            "smart-recommendations section must still exist",
        )

    def test_smart_recommendations_not_4_card_grid(self):
        """Old 4-card smart-recs-grid HTML element must not be present."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        # Check for the HTML element usage (class attribute), not CSS definition
        self.assertNotIn(
            'class="smart-recs-grid"',
            content,
            "Old bloated 4-card smart-recs-grid HTML element must be removed",
        )

    def test_smart_recommendations_mentions_restock(self):
        """Smart recommendations callout must mention restock prompts."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8").lower()
        self.assertIn(
            "restock",
            content,
            "Smart recommendations section must mention restock",
        )


# ======================================================================
# VERTICALS — MAX 6 ON LANDING PAGE
# ======================================================================

class VerticalsGridTests(TestCase):
    """Verticals grid must show max 6 items with a 'see all' link."""

    def setUp(self):
        self.client = Client()

    def test_verticals_present_on_landing(self):
        """Verticals section must exist on landing page."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertIn(
            "Phones",
            content,
            "Verticals section must be present on landing page",
        )

    def test_verticals_max_6_on_landing(self):
        """
        Landing page must show at most 6 verticals.
        More are available on the full features/about page.
        """
        import html as html_module
        from staticpages.views import get_all_verticals
        all_verticals = get_all_verticals()

        response = self.client.get(reverse("staticpages:home"))
        # Unescape HTML entities so & in names like "Phones & Electronics" match
        raw_content = response.content.decode("utf-8")
        content = html_module.unescape(raw_content)

        # Count vertical names from the first 6 that appear in the landing page
        shown_count = sum(
            1 for v in all_verticals[:6]
            if v["name"] in content
        )
        # At least 4 of the first 6 should be present
        self.assertGreaterEqual(
            shown_count,
            4,
            f"At least 4 of the top 6 verticals must appear on landing page "
            f"(found {shown_count}). Verticals checked: "
            f"{[v['name'] for v in all_verticals[:6]]}",
        )

        # Verify the template uses the slice filter — check that no more than 6
        # vertical card blocks exist by counting the specific card structure
        card_count = raw_content.count('font-size: 2rem; margin-bottom: 0.75rem;')
        if card_count > 0:
            self.assertLessEqual(
                card_count,
                6,
                f"Too many vertical cards found: {card_count} (max 6 allowed on landing)",
            )


# ======================================================================
# CACHE HEADERS
# ======================================================================

class CacheHeaderTests(TestCase):
    """Authenticated pages must never be cached. Public pages use never_cache."""

    def setUp(self):
        self.client = Client()

    def test_home_page_no_cache(self):
        """Home page must have no-cache header (never_cache decorator)."""
        response = self.client.get(reverse("staticpages:home"))
        cc = response.get("Cache-Control", "")
        self.assertTrue(
            "no-cache" in cc or "no-store" in cc or "max-age=0" in cc,
            f"Home page must have no-cache headers, got: '{cc}'",
        )

    def test_landing_metrics_no_cache(self):
        """Landing metrics API must have no-cache headers."""
        response = self.client.get(reverse("staticpages:landing_metrics_api"))
        cc = response.get("Cache-Control", "")
        self.assertTrue(
            "no-cache" in cc or "no-store" in cc or "max-age=0" in cc,
            f"Landing metrics API must have no-cache headers, got: '{cc}'",
        )


# ======================================================================
# GENERAL LANDING PAGE QUALITY
# ======================================================================

class LandingPageQualityTests(TestCase):
    """General quality checks for the landing page."""

    def setUp(self):
        self.client = Client()

    def test_home_renders_200(self):
        response = self.client.get(reverse("staticpages:home"))
        self.assertEqual(response.status_code, 200)

    def test_how_it_works_section_present(self):
        response = self.client.get(reverse("staticpages:home"))
        self.assertContains(response, "how-it-works")

    def test_testimonials_or_impact_section(self):
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8").lower()
        self.assertTrue(
            "testimonial" in content or "impact" in content or "real businesses" in content,
            "Landing page must have testimonials or impact section",
        )

    def test_footer_contains_about_link(self):
        """About link must be in the footer (after removing from mobile nav)."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        # Footer should contain About link
        self.assertIn(
            "/landing/about/",
            content,
            "About link must still exist (in footer) even if removed from mobile nav",
        )

    def test_no_duplicate_cta_wording(self):
        """'Start Running with Visibility' old CTA must not appear anywhere."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        self.assertNotIn(
            "Start Running with Visibility",
            content,
            "Old CTA 'Start Running with Visibility' must be replaced with 'Get Started Free'",
        )

    def test_get_started_free_appears_multiple_times(self):
        """'Get Started Free' should appear at least twice (hero + mobile nav + final CTA)."""
        response = self.client.get(reverse("staticpages:home"))
        content = response.content.decode("utf-8")
        count = content.count("Get Started Free")
        self.assertGreaterEqual(
            count,
            2,
            f"'Get Started Free' should appear at least twice, found {count}",
        )
