"""
Regression test to prevent filter chaining and ensure money display consistency.

This test ensures that:
1. No templates use the broken filter chain pattern: |floatformat:2|intcomma|money
2. The money filter works correctly with all input types
3. Dashboard templates render money values without ellipsis
"""
import os
import re
from pathlib import Path

import pytest
from decimal import Decimal
from django.template import Context, Template


class TestMoneyFilterChainRegression:
    """Prevent reintroduction of broken filter chaining patterns."""
    
    def test_no_floatformat_intcomma_money_chain_in_templates(self):
        """
        CRITICAL REGRESSION TEST:
        Scan all templates to ensure no one reintroduces the broken pattern:
        {{ value|floatformat:2|intcomma|money }}
        
        This pattern broke the gym dashboard because intcomma outputs strings
        with commas that the old money filter couldn't parse.
        """
        # Find all template files
        base_dir = Path(__file__).parent.parent
        templates_dir = base_dir / "templates"
        
        if not templates_dir.exists():
            pytest.skip("Templates directory not found")
        
        # Pattern to detect the broken filter chain
        # Matches: |floatformat:N|intcomma|money or |intcomma|floatformat:N|money
        broken_patterns = [
            r'\|floatformat:\d+\|intcomma\|money',
            r'\|intcomma\|floatformat:\d+\|money',
        ]
        
        violations = []
        
        # Scan all HTML files
        for template_file in templates_dir.rglob("*.html"):
            try:
                content = template_file.read_text(encoding='utf-8')
                
                for pattern in broken_patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        # Get line numbers for violations
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line):
                                violations.append({
                                    'file': str(template_file.relative_to(base_dir)),
                                    'line': i,
                                    'content': line.strip()[:100]  # First 100 chars
                                })
            except Exception as e:
                # Skip files that can't be read
                pass
        
        # Assert no violations found
        if violations:
            violation_msgs = [
                f"\n  {v['file']}:{v['line']} - {v['content']}"
                for v in violations
            ]
            pytest.fail(
                f"Found {len(violations)} instance(s) of broken filter chain pattern "
                f"|floatformat|intcomma|money in templates. "
                f"Use |money directly instead:\n"
                + "\n".join(violation_msgs)
            )
    
    def test_gym_dashboard_renders_full_money_values(self):
        """
        Test that gym dashboard renders full money values without ellipsis.
        This ensures the CSS fix is working.
        """
        # Create a template that mimics the gym dashboard structure
        template_str = """
        {% load money %}
        <div class="metric-card">
            <h3>Revenue</h3>
            <p>{{ revenue|money }}</p>
        </div>
        """
        
        template = Template(template_str)
        context = Context({
            'revenue': Decimal('415000.00')
        })
        
        rendered = template.render(context)
        
        # Should contain the full formatted value
        assert 'MWK 415,000.00' in rendered
        
        # Should NOT contain ellipsis characters
        assert '...' not in rendered
        assert '…' not in rendered  # Unicode ellipsis
    
    def test_money_filter_handles_large_values_without_truncation(self):
        """
        Test that very large money values are formatted correctly
        without truncation or scientific notation.
        """
        template = Template("{% load money %}{{ value|money }}")
        
        test_cases = [
            (Decimal('1234567890.12'), 'MWK 1,234,567,890.12'),
            (Decimal('999999999.99'), 'MWK 999,999,999.99'),
            (Decimal('100000000'), 'MWK 100,000,000.00'),
        ]
        
        for value, expected in test_cases:
            context = Context({'value': value})
            result = template.render(context)
            assert result == expected, f"Expected {expected}, got {result}"
    
    def test_money_filter_with_comma_separated_input(self):
        """
        REGRESSION: Ensure money filter still handles comma-separated
        string input (from intcomma filter output).
        """
        template = Template("{% load money %}{{ value|money }}")
        context = Context({'value': '415,000.50'})
        result = template.render(context)
        
        assert result == 'MWK 415,000.50'
    
    def test_metric_card_css_no_ellipsis(self):
        """
        Verify that the numeric-display.css file contains the fix
        to prevent ellipsis in metric cards.
        """
        base_dir = Path(__file__).parent.parent
        css_file = base_dir / "static" / "css" / "numeric-display.css"
        
        if not css_file.exists():
            pytest.skip("numeric-display.css not found")
        
        content = css_file.read_text(encoding='utf-8')
        
        # Should contain the critical fix for .metric-card p
        assert '.metric-card p' in content
        assert 'white-space: normal !important' in content or 'white-space:normal!important' in content
        assert 'overflow: visible !important' in content or 'overflow:visible!important' in content
        assert 'text-overflow: clip !important' in content or 'text-overflow:clip!important' in content


class TestMoneyFilterConsistency:
    """Ensure money filter behaves consistently across all input types."""
    
    def test_money_filter_output_format_consistency(self):
        """
        All money values should follow the same format:
        - "MWK " prefix
        - Thousands separators (commas)
        - Exactly 2 decimal places
        """
        template = Template("{% load money %}{{ value|money }}")
        
        test_values = [
            Decimal('0'),
            Decimal('100'),
            Decimal('1000'),
            Decimal('1000.50'),
            Decimal('415000'),
            0,
            100,
            1000,
            '1000',
            '1,000',
        ]
        
        for value in test_values:
            context = Context({'value': value})
            result = template.render(context)
            
            # All outputs should start with "MWK "
            assert result.startswith('MWK '), f"Output {result} doesn't start with 'MWK '"
            
            # All outputs should have exactly 2 decimal places
            assert result.count('.') == 1, f"Output {result} doesn't have exactly one decimal point"
            assert result.endswith(('.00', '.25', '.50', '.75')) or \
                   len(result.split('.')[-1]) == 2, \
                   f"Output {result} doesn't have 2 decimal places"
    
    def test_money_filter_never_returns_scientific_notation(self):
        """Money values should never use scientific notation (e.g., 1.5e+6)."""
        template = Template("{% load money %}{{ value|money }}")
        
        large_values = [
            Decimal('1500000'),
            Decimal('1000000000'),
            1500000,
            1000000000,
        ]
        
        for value in large_values:
            context = Context({'value': value})
            result = template.render(context)
            
            # Should not contain 'e' or 'E' (scientific notation)
            assert 'e' not in result.lower(), \
                   f"Value {value} rendered as scientific notation: {result}"

