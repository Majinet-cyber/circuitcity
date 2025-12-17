"""
Safe template tag for rendering brand icons with fallback support.

Prevents 500 errors from missing brand SVG files by checking existence
before returning the URL. Always falls back to a default icon if the
specific brand icon is not found.

Usage:
    {% load brand_icons %}
    <img src="{% brand_icon brand_name %}" alt="Brand Logo">

Examples:
    {% brand_icon "iPhone" %}        -> img/brands/iphone.svg
    {% brand_icon "Google Pixel" %}  -> img/brands/google-pixel.svg
    {% brand_icon "Redmi" %}         -> img/brands/redmi.svg
    {% brand_icon "Unknown Brand" %} -> img/brands/default.svg (fallback)
"""

from django import template
from django.templatetags.static import static
from django.utils.text import slugify
from django.contrib.staticfiles.storage import staticfiles_storage

register = template.Library()


@register.simple_tag
def brand_icon(brand_name: str) -> str:
    """
    Return the URL for a brand icon SVG, with safe fallback.
    
    Args:
        brand_name: The brand name (e.g., "iPhone", "Google Pixel", "Redmi")
    
    Returns:
        str: URL to the brand SVG file, or default.svg if not found
    
    Process:
        1. Slugify the brand name to get lowercase, hyphenated version
        2. Build the path: img/brands/<slug>.svg
        3. Check if file exists using staticfiles_storage.exists()
        4. Return URL if exists, otherwise return default.svg fallback
        5. NEVER raise - always return a valid URL
    """
    # Fallback path
    fallback_path = "img/brands/default.svg"
    
    try:
        # Handle None or empty brand names
        if not brand_name:
            return static(fallback_path)
        
        # Slugify the brand name (lowercase, hyphenated)
        # e.g., "iPhone" -> "iphone", "Google Pixel" -> "google-pixel"
        slug = slugify(brand_name)
        
        # Handle empty slugs (e.g., brand name with only special chars)
        if not slug:
            return static(fallback_path)
        
        # Build the brand icon path
        brand_path = f"img/brands/{slug}.svg"
        
        # Check if the file exists before trying to get its URL
        # This prevents WhiteNoise from raising ValueError on missing files
        if staticfiles_storage.exists(brand_path):
            return staticfiles_storage.url(brand_path)
        else:
            # File doesn't exist, use fallback
            return static(fallback_path)
    
    except Exception:
        # Catch-all safety net: if anything goes wrong, return fallback
        # This ensures we NEVER cause a 500 error from a missing icon
        return static(fallback_path)


@register.simple_tag
def brand_icon_path(brand_logo_path: str) -> str:
    """
    Safely return the URL for a brand icon path, with existence checking.
    
    This is an alternative version that accepts a full path (e.g., from 
    the brands dict: "img/brands/iphone.svg") instead of just the brand name.
    
    Args:
        brand_logo_path: Full path to the brand logo (e.g., "img/brands/iphone.svg")
    
    Returns:
        str: URL to the brand SVG file, or default.svg if not found
    
    Usage:
        {% brand_icon_path brand.logo %}
    """
    fallback_path = "img/brands/default.svg"
    
    try:
        # Handle None or empty paths
        if not brand_logo_path:
            return static(fallback_path)
        
        # Check if the file exists
        if staticfiles_storage.exists(brand_logo_path):
            return staticfiles_storage.url(brand_logo_path)
        else:
            # File doesn't exist, use fallback
            return static(fallback_path)
    
    except Exception:
        # Catch-all safety net
        return static(fallback_path)

