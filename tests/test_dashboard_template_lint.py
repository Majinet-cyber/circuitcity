"""
Lint check for dashboard templates to ensure no legacy UPPERCASE variables.

This test scans all dashboard templates and fails if it finds references to
uppercase dashboard context variables (YESTERDAY_SUMMARY, DASHBOARD_QUOTES, etc.).

All templates should use lowercase keys going forward: yesterday_summary, dashboard_quotes, etc.
"""
import os
import re
import pytest
from pathlib import Path


# Legacy uppercase variable patterns to detect
FORBIDDEN_PATTERNS = [
    r'\bYESTERDAY_SUMMARY\b',
    r'\bDASHBOARD_QUOTES\b',
    r'\bDASHBOARD_BRAND_TITLE\b',
    r'\bDASHBOARD_BRAND_LOGO_URL\b',
    r'\bDASHBOARD_GREETING\b',
    r'\bDASHBOARD_USER_NAME\b',
    r'\bDASHBOARD_SHOW_WELCOME\b',
    r'\bDASHBOARD_MILESTONE_MESSAGE\b',
    r'\bPAYMENT_MIX\b',  # Should be payment_mix (lowercase)
    r'\bPAYMENT_MIX_PERIOD\b',
]


def find_template_files(base_dir: Path) -> list[Path]:
    """
    Find all dashboard-related template files.
    
    Args:
        base_dir: Base directory to search from (project root)
    
    Returns:
        List of Path objects for dashboard templates
    """
    template_patterns = [
        "templates/verticals/**/dashboard*.html",
        "templates/dashboard/**/*.html",
        "templates/partials/dashboard*.html",
    ]
    
    files = []
    for pattern in template_patterns:
        files.extend(base_dir.glob(pattern))
    
    return files


def scan_template_for_uppercase_vars(template_path: Path) -> list[tuple[int, str, str]]:
    """
    Scan a template file for forbidden uppercase dashboard variables.
    
    Args:
        template_path: Path to template file
    
    Returns:
        List of (line_number, line_content, matched_pattern) tuples
    """
    violations = []
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                # Skip comment lines
                if line.strip().startswith('{#') or line.strip().startswith('{% comment %}'):
                    continue
                
                # Check for forbidden patterns
                for pattern in FORBIDDEN_PATTERNS:
                    if re.search(pattern, line):
                        violations.append((line_num, line.strip(), pattern))
    except Exception as e:
        # If we can't read the file, log but don't fail
        print(f"Warning: Could not read {template_path}: {e}")
    
    return violations


@pytest.mark.lint
def test_no_uppercase_dashboard_vars_in_templates():
    """
    Lint test: Ensure no dashboard templates use legacy UPPERCASE variable names.
    
    This test helps enforce the new standard of lowercase_snake_case for all
    dashboard context variables.
    
    If this test fails:
    1. Find the template file listed in the error
    2. Replace UPPERCASE variables with lowercase equivalents:
       - YESTERDAY_SUMMARY → yesterday_summary
       - DASHBOARD_QUOTES → dashboard_quotes
       - DASHBOARD_BRAND_TITLE → dashboard_brand_title
       - etc.
    3. The normalize_dashboard_context() helper ensures both work during transition
    """
    # Find project root (where manage.py is)
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent  # Go up from tests/ to project root
    
    # Find all dashboard templates
    template_files = find_template_files(project_root)
    
    assert len(template_files) > 0, "No dashboard templates found - check glob patterns"
    
    # Scan each template
    all_violations = {}
    for template_file in template_files:
        violations = scan_template_for_uppercase_vars(template_file)
        if violations:
            # Store relative path for cleaner output
            rel_path = template_file.relative_to(project_root)
            all_violations[str(rel_path)] = violations
    
    # Build detailed error message
    if all_violations:
        error_lines = ["❌ Found legacy UPPERCASE dashboard variables in templates:"]
        error_lines.append("")
        error_lines.append("The following templates need to be updated to use lowercase keys:")
        error_lines.append("")
        
        for template_path, violations in all_violations.items():
            error_lines.append(f"📄 {template_path}")
            for line_num, line_content, pattern in violations:
                error_lines.append(f"   Line {line_num}: {line_content[:80]}")
                error_lines.append(f"             ^ Found pattern: {pattern}")
            error_lines.append("")
        
        error_lines.append("🔧 How to fix:")
        error_lines.append("   Replace UPPERCASE variables with lowercase equivalents:")
        error_lines.append("   - YESTERDAY_SUMMARY → yesterday_summary")
        error_lines.append("   - DASHBOARD_QUOTES → dashboard_quotes")
        error_lines.append("   - DASHBOARD_BRAND_TITLE → dashboard_brand_title")
        error_lines.append("   - DASHBOARD_GREETING → dashboard_greeting")
        error_lines.append("   - etc.")
        error_lines.append("")
        error_lines.append("   The normalize_dashboard_context() helper ensures both work during transition.")
        
        pytest.fail("\n".join(error_lines))


@pytest.mark.lint
def test_dashboard_templates_exist():
    """Sanity check: ensure we can find dashboard templates."""
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    
    template_files = find_template_files(project_root)
    
    # We should find at least 5 dashboard templates (one per vertical)
    assert len(template_files) >= 5, (
        f"Expected at least 5 dashboard templates, found {len(template_files)}. "
        "Check glob patterns in find_template_files()."
    )
    
    print(f"✓ Found {len(template_files)} dashboard templates:")
    for tf in template_files:
        print(f"  - {tf.relative_to(project_root)}")


if __name__ == "__main__":
    """
    Run this script directly to see which templates have violations:
    
        python tests/test_dashboard_template_lint.py
    """
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    
    template_files = find_template_files(project_root)
    print(f"Scanning {len(template_files)} dashboard templates...\n")
    
    found_violations = False
    for template_file in template_files:
        violations = scan_template_for_uppercase_vars(template_file)
        if violations:
            found_violations = True
            rel_path = template_file.relative_to(project_root)
            print(f"❌ {rel_path}")
            for line_num, line_content, pattern in violations:
                print(f"   Line {line_num}: {line_content[:80]}")
                print(f"             ^ {pattern}")
            print()
    
    if not found_violations:
        print("✅ All dashboard templates are using lowercase variable names!")
    else:
        print("\n⚠️  Found uppercase dashboard variables. Please fix them as shown above.")
        exit(1)

