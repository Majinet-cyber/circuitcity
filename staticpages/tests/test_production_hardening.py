"""
Production hardening tests for EMAJINET landing page, platform reliability,
and Renewable Energy flagship section.

Covers:
- Renewable Energy flagship section present and correctly positioned
- Energy section contains correct capability headings
- Energy CTA link is valid
- Landing metrics API endpoint schema and response
- Hero section has no zero-flash placeholders
- Mobile nav is lean (no footer clutter)
- Pricing snapshot present on landing page with real prices
- Data carousel replaced by compact callout (no old carousel DOM)
- Smart Recommendations section is compact (no bloated 4-card grid)
- CTA wording consistency ("Get Started Free")
- Cache headers for authenticated pages (no-cache)

NON-NEGOTIABLE: All tests must pass before deployment.

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


class RenewableEnergyFlagshipTests(TestCase):
    """
    Renewable Energy flagship section tests.

    Rules enforced:
    - Light mode (no dark gradient background)
    - No extra 'Get Started Free' button inside the section
    - Has a subtle 'Explore Renewable Energy' link only
    - All 4 capabilities present
    - Correct document order (after How It Works, before Simulator)
    - Flagship label + engineering headline present
    - Portfolio proof strip present
    - Page renders HTTP 200
    """

    def setUp(self):
        self.client = Client()
        self.response = self.client.get(reverse("staticpages:home"))
        self.content = self.response.content.decode("utf-8")

    def test_energy_section_present(self):
        self.assertIn(
            'id="renewable-energy"',
            self.content,
            "Renewable Energy section (#renewable-energy) must exist on landing page",
        )

    def test_energy_flagship_label(self):
        self.assertIn(
            "Flagship Vertical",
            self.content,
            "'Flagship Vertical' label must appear in the energy section",
        )

    def test_energy_headline_present(self):
        self.assertIn(
            "Engineering-grade intelligence",
            self.content,
            "Energy section headline must be present",
        )

    def test_system_sizing_capability_present(self):
        self.assertIn(
            "System Sizing Engine",
            self.content,
            "System Sizing Engine capability must be in energy section",
        )

    def test_predictive_maintenance_present(self):
        self.assertIn(
            "Predictive Maintenance",
            self.content,
            "Predictive Maintenance capability must be in energy section",
        )

    def test_load_forecasting_present(self):
        self.assertIn(
            "Demand",
            self.content,
            "Demand & Load Forecasting must be in energy section",
        )

    def test_energy_economics_present(self):
        self.assertIn(
            "Energy Economics",
            self.content,
            "Energy Economics & ROI capability must be in energy section",
        )

    def test_no_extra_cta_button_inside_energy_section(self):
        """Energy section must NOT contain a standalone 'Get Started Free' button.
        The page-level CTA is fine; the energy section should only have a subtle link."""
        # Isolate the energy section HTML
        energy_start = self.content.find('id="renewable-energy"')
        energy_end = self.content.find('id="business-simulator"')
        self.assertGreater(energy_start, -1, "#renewable-energy must exist")
        self.assertGreater(energy_end, energy_start, "#business-simulator must come after energy")
        energy_html = self.content[energy_start:energy_end]
        # Must NOT have "Get Started Free" as a button inside the energy section
        self.assertNotIn(
            "Get Started Free",
            energy_html,
            "Energy section must NOT have an extra 'Get Started Free' button — use subtle link only",
        )

    def test_explore_link_present_in_energy_section(self):
        """Energy section must contain the subtle 'Explore Renewable Energy' link."""
        self.assertIn(
            "Explore Renewable Energy",
            self.content,
            "Energy section must have 'Explore Renewable Energy' subtle link",
        )

    def test_energy_is_light_mode(self):
        """Energy section must NOT use a dark gradient background (light mode required)."""
        energy_start = self.content.find('id="renewable-energy"')
        energy_end = self.content.find('id="business-simulator"')
        energy_html = self.content[energy_start:energy_end]
        self.assertNotIn(
            "#0d1a2e",
            energy_html,
            "Energy section must be light mode — dark navy color #0d1a2e must not appear",
        )
        self.assertNotIn(
            "#0f2613",
            energy_html,
            "Energy section must be light mode — dark green #0f2613 must not appear",
        )

    def test_energy_section_positioned_after_how_it_works(self):
        how_it_works_pos = self.content.find('id="how-it-works"')
        energy_pos = self.content.find('id="renewable-energy"')
        self.assertGreater(how_it_works_pos, -1, "#how-it-works must exist")
        self.assertGreater(energy_pos, -1, "#renewable-energy must exist")
        self.assertGreater(
            energy_pos, how_it_works_pos,
            "Renewable Energy section must appear AFTER How It Works",
        )

    def test_energy_section_before_simulator(self):
        energy_pos = self.content.find('id="renewable-energy"')
        simulator_pos = self.content.find('id="business-simulator"')
        self.assertGreater(simulator_pos, -1, "#business-simulator must exist")
        self.assertGreater(energy_pos, -1, "#renewable-energy must exist")
        self.assertGreater(
            simulator_pos, energy_pos,
            "Business simulator must appear AFTER the Renewable Energy section",
        )

    def test_portfolio_proof_strip_present(self):
        self.assertIn(
            "Portfolio-level command center",
            self.content,
            "Energy proof strip must mention portfolio capabilities",
        )

    def test_landing_page_renders_200(self):
        self.assertEqual(self.response.status_code, 200)


class LiveMetricsNeverBlankTests(TestCase):
    """
    Ensure the landing page metrics block never shows blank / dash / zero.

    The metrics container (#liveMetricsContainer) must always be present.
    The template must not render literal '—' (em dash) as a metric value.
    The JS live metrics endpoint must return the correct schema.
    """

    def setUp(self):
        self.client = Client()
        self.response = self.client.get(reverse("staticpages:home"))
        self.content = self.response.content.decode("utf-8")

    def test_live_metrics_container_always_rendered(self):
        """#liveMetricsContainer must ALWAYS be present regardless of has_data."""
        self.assertIn(
            'id="liveMetricsContainer"',
            self.content,
            "#liveMetricsContainer must always be in the DOM for JS to target",
        )

    def test_live_metrics_note_element_present(self):
        """#liveMetricsNote must always be present."""
        self.assertIn(
            'id="liveMetricsNote"',
            self.content,
            "#liveMetricsNote must always be in the DOM",
        )

    def test_no_raw_dash_as_metric_value_in_container(self):
        """The hero-counter-value divs must not contain a bare '—' as text content.
        Skeleton spans are OK; em dashes as decorative text are OK; but NOT as a metric value."""
        # Find liveMetricsContainer block
        start = self.content.find('id="liveMetricsContainer"')
        end = self.content.find('id="liveMetricsNote"')
        if start == -1 or end == -1:
            self.fail("Could not locate liveMetricsContainer or liveMetricsNote in page")
        container_html = self.content[start:end]
        # The old pattern: <div class="hero-counter-value" style="...">—</div>
        # Check for that exact pattern (style attribute implies it was the fallback div)
        import re
        dash_fallback = re.search(
            r'hero-counter-value[^>]*style[^>]*>[^<]*\u2014[^<]*</',
            container_html,
        )
        self.assertIsNone(
            dash_fallback,
            "hero-counter-value must not contain a bare '—' em dash as the metric value",
        )

    def test_lm_skeleton_class_exists_in_page(self):
        """lm-skeleton CSS class must be defined in the page (for shimmer loading state)."""
        self.assertIn(
            "lm-skeleton",
            self.content,
            ".lm-skeleton class must be defined for skeleton loading animation",
        )

    def test_metrics_api_has_correct_schema(self):
        """landing_metrics_api must return JSON with all required fields."""
        import json
        resp = self.client.get(reverse("staticpages:landing_metrics_api"))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        required_fields = [
            "active_businesses", "team_members",
            "avg_daily_revenue", "sales_recorded_per_day",
            "avg_margin_visibility", "has_data", "as_of", "status",
        ]
        for field in required_fields:
            self.assertIn(field, data, f"landing_metrics_api response missing field: {field}")

    def test_metrics_api_status_success(self):
        """landing_metrics_api must return status='success'."""
        import json
        resp = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(resp.content)
        self.assertEqual(data.get("status"), "success")

    def test_metrics_api_active_businesses_non_negative(self):
        """active_businesses must be a non-negative integer."""
        import json
        resp = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(resp.content)
        val = data.get("active_businesses", -1)
        self.assertGreaterEqual(val, 0, "active_businesses must be >= 0")

    def test_metrics_api_has_data_is_bool(self):
        """has_data must be a boolean."""
        import json
        resp = self.client.get(reverse("staticpages:landing_metrics_api"))
        data = json.loads(resp.content)
        self.assertIsInstance(data.get("has_data"), bool, "has_data must be a boolean")
