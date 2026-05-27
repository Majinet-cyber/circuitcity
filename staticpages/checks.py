"""
Django system checks for static file integrity.

These checks run automatically during `manage.py check` and at startup in
DEBUG mode. They verify that every statically-referenced image in
publicfacing templates actually exists in STATICFILES_DIRS, preventing
the `ValueError: The file '...' could not be found with
CompressedManifestStaticFilesStorage` crash that caused the /landing/ 500.

These checks are tagged 'staticfiles' so they can be silenced selectively:
    python manage.py check --silenced-checks staticfiles.E001
"""

import pathlib

from django.conf import settings
from django.core.checks import Error, Warning, register


# ---------------------------------------------------------------------------
# Catalogue of every static path that a public template references.
# Keep this list in sync with templates whenever an image is added/removed.
# ---------------------------------------------------------------------------
REQUIRED_STATIC_ASSETS: list[tuple[str, str]] = [
    # (static-relative path,                    used-in template)
    ("img/partners/paychangu-logo.svg",         "staticpages/home.html"),
    ("img/partners/airtel-logo.svg",            "staticpages/home.html"),
    ("img/majn.png",                            "staticpages/home.html + many"),
    ("img/logo-32.png",                         "templates/base.html"),
    ("img/user-circle.svg",                     "templates/partials/topbar_user.html"),
    ("img/car-dealer/car-green.svg",            "templates/car_dealer/*.html"),
    ("img/brands/default.svg",                  "templates/inventory/add_product_phones_v2.html"),
    ("img/cfo_happy.gif",                       "staticpages/partials/cfo_assistant.html"),
    ("img/cfo_neutral.gif",                     "staticpages/partials/cfo_assistant.html"),
]

# Every value that get_cfo_mood() can return must map to an existing file.
CFO_MOODS = ("happy", "neutral")


def _static_dirs() -> list[pathlib.Path]:
    """Return the list of source static directories that actually exist."""
    return [
        pathlib.Path(d)
        for d in getattr(settings, "STATICFILES_DIRS", [])
        if pathlib.Path(d).exists()
    ]


def _find_in_static(relative: str) -> bool:
    """Return True if `relative` resolves to a real file in any STATICFILES_DIR."""
    for base in _static_dirs():
        if (base / relative).is_file():
            return True
    return False


@register("staticfiles")
def check_required_static_assets(app_configs, **kwargs):
    """
    Verify that every catalogued static path has a real backing file.
    Runs as an Error (not Warning) so `manage.py check` exits non-zero when
    a file is missing, catching regressions before deployment.
    """
    errors = []
    for rel_path, template in REQUIRED_STATIC_ASSETS:
        if not _find_in_static(rel_path):
            errors.append(
                Error(
                    f"Missing static asset: '{rel_path}'",
                    hint=(
                        f"Referenced in {template}. "
                        f"Add the file to one of STATICFILES_DIRS or update the template. "
                        f"Missing files crash production with CompressedManifestStaticFilesStorage."
                    ),
                    id="staticfiles.E001",
                )
            )
    return errors


@register("staticfiles")
def check_cfo_mood_assets(app_configs, **kwargs):
    """
    Verify that every possible CFO mood value maps to an existing GIF.
    get_cfo_mood() must only return moods that have a backing file.
    """
    errors = []
    for mood in CFO_MOODS:
        rel_path = f"img/cfo_{mood}.gif"
        if not _find_in_static(rel_path):
            errors.append(
                Error(
                    f"Missing CFO mood asset: '{rel_path}'",
                    hint=(
                        f"get_cfo_mood() can return '{mood}' but "
                        f"static/{rel_path} does not exist. "
                        f"Add the file or remove '{mood}' from CFO_MOODS in staticpages/checks.py."
                    ),
                    id="staticfiles.E002",
                )
            )
    return errors


@register("staticfiles")
def check_no_old_partner_png_references(app_configs, **kwargs):
    """
    Warn if the old broken .png partner paths somehow re-appear in source.
    These were the original cause of the /landing/ 500.
    """
    import re

    broken_patterns = [
        r"img/partners/paychangu\.png",
        r"img/partners/airtel\.png",
    ]
    warnings = []
    template_roots = [
        pathlib.Path(settings.BASE_DIR) / "staticpages" / "templates",
        pathlib.Path(settings.BASE_DIR) / "templates",
    ]
    for root in template_roots:
        if not root.exists():
            continue
        for html_file in root.rglob("*.html"):
            text = html_file.read_text(encoding="utf-8", errors="ignore")
            for pattern in broken_patterns:
                if re.search(pattern, text):
                    warnings.append(
                        Warning(
                            f"Broken static reference found in {html_file.name}: matches '{pattern}'",
                            hint=(
                                "These .png files do not exist. "
                                "Use paychangu-logo.svg / airtel-logo.svg instead."
                            ),
                            id="staticfiles.W001",
                        )
                    )
    return warnings
