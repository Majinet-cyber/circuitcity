"""
Template compilation tests to catch Django TemplateSyntaxError issues.

These tests ensure that templates compile and render without syntax errors,
specifically catching issues like:
- Invalid block tag nesting (e.g., {% endwith %} inside unclosed {% if %})
- Mismatched opening/closing tags
- Orphan {% endwith %} or {% endif %} tags
- Missing filter arguments
- Invalid pagination syntax
- Missing {% load %} statements for templatetags/filters
- {% extends %} not being the first tag
"""
from django.test import SimpleTestCase
from django.template.loader import get_template
from pathlib import Path


class TemplateCompileTests(SimpleTestCase):
    def test_all_templates_compile(self):
        """
        Test that ALL templates in the templates directory compile without syntax errors.
        
        This is a regression test to ensure no template has syntax errors that would
        cause a 500 error when rendering pages.
        """
        templates_root = Path('templates')
        bad_templates = []
        
        for template_path in templates_root.rglob('*.html'):
            if template_path.is_file():
                template_name = template_path.relative_to(templates_root).as_posix()
                try:
                    get_template(template_name)
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e).splitlines()[-1] if str(e).splitlines() else str(e)
                    bad_templates.append((template_name, error_type, error_msg))
        
        # If any templates failed, create a readable error message
        if bad_templates:
            error_lines = [f"\n{len(bad_templates)} template(s) failed to compile:"]
            for name, error_type, msg in bad_templates:
                error_lines.append(f"  - {name}")
                error_lines.append(f"    {error_type}: {msg}")
            self.fail('\n'.join(error_lines))
    
    def test_critical_templates_compile(self):
        """
        Test that critical templates that had compilation issues compile correctly.
        
        This specifically tests templates that were previously failing:
        - accounts/_settings_shell.html: {% extends %} must be first
        - partials/dashboard_kpis.html: wallet_money filter + missing {% load static %}
        - partials/kpi_card_clickable.html: wallet_money filter
        - partials/smart_pricing_feedback.html: missing {% load static %}
        """
        critical_templates = [
            'accounts/_settings_shell.html',
            'partials/dashboard_kpis.html',
            'partials/kpi_card_clickable.html',
            'partials/smart_pricing_feedback.html',
        ]
        
        for template_name in critical_templates:
            with self.subTest(template=template_name):
                try:
                    template = get_template(template_name)
                    # Successfully getting the template means it compiled without errors
                    self.assertIsNotNone(template)
                except Exception as e:
                    self.fail(
                        f"Template '{template_name}' failed to compile:\n"
                        f"  {type(e).__name__}: {e}"
                    )
    
    def test_phones_dashboard_template_compiles(self):
        """
        Test that phones dashboard template compiles without syntax errors.
        
        The test:
        1. Compiles the template (catches syntax errors at parse time)
        2. Renders it with mock context (catches runtime template errors)
        """
        template = get_template("verticals/phones/dashboard.html")
        
        # Test that the template can render with minimal context
        # This catches runtime template errors that compilation alone might miss
        mock_context = {
            'business': {'name': 'Test Business'},
            'location_label': 'Test Location',
            'hero_title': 'Test Title',
            'hero_blurb': 'Test Blurb',
            'IS_MANAGER': True,
            'dashboard_kpis': {
                'range_key': 'today',
                'range_label': 'Today',
                'start_date': None,
                'end_date': None,
                'stock_on_hand': 0,
                'units_sold': 0,
                'revenue': 0,
                'total_costs': 0,
                'cost_of_goods': 0,
                'business_costs': 0,
                'profit': 0,
                'profit_margin': 0,
                'payment_mix': {},
                'stock_potential_profit': 0,
            },
            'fast_models': [],
            'sales_by_model': [],
            'top_agents': [],
            'best_sales_day': None,
            'sales_trend_json': '[]',
            'quotes_json': '[]',
        }
        
        # Render the template - this will raise TemplateSyntaxError if there are nesting issues
        try:
            rendered = template.render(mock_context)
            # Verify we got some output (template actually rendered)
            self.assertIsNotNone(rendered)
            self.assertGreater(len(rendered), 0)
        except Exception as e:
            # If there's a template syntax error, fail with a clear message
            error_type = type(e).__name__
            if 'TemplateSyntaxError' in error_type or 'Invalid block tag' in str(e):
                self.fail(f"Template has syntax error: {e}")
            # Re-raise other exceptions for debugging
            raise

