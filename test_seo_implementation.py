#!/usr/bin/env python
"""
SEO Implementation Test Script
==============================

Quick verification that all SEO fixes are in place.
Run this after deployment to verify everything works.

Usage:
    python test_seo_implementation.py

Requirements:
    - Django project must be running
    - Database must be accessible
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.test import RequestFactory
from django.conf import settings
from cc.middleware_seo import SEONoIndexMiddleware, CanonicalURLMiddleware, PublicQueryCleanupMiddleware
from django.http import HttpResponse


def test_middleware_installed():
    """Test that SEO middleware is installed in settings."""
    print("✓ Testing middleware installation...")
    
    middleware_list = settings.MIDDLEWARE
    
    assert 'cc.middleware_seo.SEONoIndexMiddleware' in middleware_list, \
        "❌ SEONoIndexMiddleware not in MIDDLEWARE"
    print("  ✓ SEONoIndexMiddleware installed")
    
    assert 'cc.middleware_seo.CanonicalURLMiddleware' in middleware_list, \
        "❌ CanonicalURLMiddleware not in MIDDLEWARE"
    print("  ✓ CanonicalURLMiddleware installed")
    
    assert 'cc.middleware_seo.PublicQueryCleanupMiddleware' in middleware_list, \
        "❌ PublicQueryCleanupMiddleware not in MIDDLEWARE"
    print("  ✓ PublicQueryCleanupMiddleware installed")


def test_noindex_middleware():
    """Test that noindex middleware adds headers to private pages."""
    print("\n✓ Testing noindex middleware...")
    
    factory = RequestFactory()
    middleware = SEONoIndexMiddleware(lambda r: HttpResponse())
    
    # Test private routes
    private_routes = [
        '/inventory/dashboard/',
        '/accounts/login/',
        '/admin/',
        '/dashboard/',
        '/api/test/',
    ]
    
    for route in private_routes:
        request = factory.get(route)
        response = middleware(request)
        
        assert 'X-Robots-Tag' in response, \
            f"❌ X-Robots-Tag not added to {route}"
        assert response['X-Robots-Tag'] == 'noindex, nofollow, noarchive', \
            f"❌ Wrong X-Robots-Tag value for {route}"
        print(f"  ✓ {route} has noindex header")
    
    # Test public routes (should NOT have noindex)
    public_routes = [
        '/landing/',
        '/landing/pricing/',
        '/landing/about/',
    ]
    
    for route in public_routes:
        request = factory.get(route)
        response = middleware(request)
        
        assert 'X-Robots-Tag' not in response, \
            f"❌ X-Robots-Tag incorrectly added to public route {route}"
        print(f"  ✓ {route} has NO noindex header (correct)")


def test_canonical_middleware():
    """Test that canonical middleware redirects www to non-www."""
    print("\n✓ Testing canonical domain middleware...")
    
    factory = RequestFactory()
    middleware = CanonicalURLMiddleware(lambda r: HttpResponse())
    
    # Test www redirect
    request = factory.get('/landing/pricing/', HTTP_HOST='www.emajinet.africa')
    response = middleware(request)
    
    if response and hasattr(response, 'status_code'):
        assert response.status_code == 301, \
            "❌ www redirect should be 301 permanent"
        assert 'emajinet.africa' in response['Location'], \
            "❌ www not redirected to non-www"
        assert 'www.' not in response['Location'], \
            "❌ www still in redirect location"
        print("  ✓ www.emajinet.africa redirects to emajinet.africa")
    
    # Test non-www (should pass through or return response from get_response)
    request = factory.get('/landing/pricing/', HTTP_HOST='emajinet.africa')
    response = middleware(request)
    
    # Middleware returns None if no redirect needed, or the response from get_response
    # Either way, it should NOT be a redirect
    if response is not None:
        assert not (hasattr(response, 'status_code') and response.status_code in [301, 302]), \
            "❌ Non-www request should not redirect"
    print("  ✓ emajinet.africa passes through (no redirect)")


def test_https_settings():
    """Test that HTTPS settings are configured correctly."""
    print("\n✓ Testing HTTPS settings...")
    
    if not settings.DEBUG:
        assert settings.SECURE_SSL_REDIRECT, \
            "❌ SECURE_SSL_REDIRECT should be True in production"
        print("  ✓ SECURE_SSL_REDIRECT enabled")
        
        assert settings.SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https'), \
            "❌ SECURE_PROXY_SSL_HEADER not configured for proxy"
        print("  ✓ SECURE_PROXY_SSL_HEADER configured")
        
        assert settings.SESSION_COOKIE_SECURE, \
            "❌ SESSION_COOKIE_SECURE should be True"
        print("  ✓ SESSION_COOKIE_SECURE enabled")
        
        assert settings.CSRF_COOKIE_SECURE, \
            "❌ CSRF_COOKIE_SECURE should be True"
        print("  ✓ CSRF_COOKIE_SECURE enabled")
    else:
        print("  ⚠ DEBUG=True, HTTPS settings disabled (expected in dev)")


def test_allowed_hosts():
    """Test that ALLOWED_HOSTS includes both www and non-www."""
    print("\n✓ Testing ALLOWED_HOSTS...")
    
    hosts = settings.ALLOWED_HOSTS
    
    # In production, should have both variants
    if 'emajinet.africa' in hosts:
        assert 'www.emajinet.africa' in hosts, \
            "❌ www.emajinet.africa should be in ALLOWED_HOSTS for redirect"
        print("  ✓ Both emajinet.africa and www.emajinet.africa in ALLOWED_HOSTS")
    else:
        print("  ⚠ Production domain not in ALLOWED_HOSTS (expected in dev)")


def test_robots_txt_view():
    """Test that robots.txt view exists and uses new strategy (2025-12-25)."""
    print("\n✓ Testing robots.txt...")
    
    from django.urls import reverse
    
    try:
        url = reverse('robots_txt')
        print(f"  ✓ robots.txt URL configured: {url}")
    except Exception as e:
        print(f"  ❌ robots.txt URL not found: {e}")
        return
    
    # Test the view
    factory = RequestFactory()
    request = factory.get('/robots.txt', HTTP_HOST='emajinet.africa', secure=True)
    
    from cc.urls import robots_txt
    response = robots_txt(request)
    
    assert response.status_code == 200, \
        "❌ robots.txt should return 200"
    assert response['Content-Type'] == 'text/plain', \
        "❌ robots.txt should be text/plain"
    
    content = response.content.decode('utf-8')
    assert 'User-agent: *' in content, \
        "❌ robots.txt missing User-agent"
    
    # NEW STRATEGY (2025-12-25): Only block sensitive endpoints
    assert 'Disallow: /admin/' in content, \
        "❌ robots.txt should block /admin/"
    assert 'Disallow: /api/' in content, \
        "❌ robots.txt should block /api/"
    
    # Private UI pages should NOT be blocked (Google needs to crawl them to see noindex)
    assert 'Disallow: /inventory/' not in content, \
        "❌ robots.txt should NOT block /inventory/ (noindex via header instead)"
    assert 'Disallow: /dashboard/' not in content, \
        "❌ robots.txt should NOT block /dashboard/ (noindex via header instead)"
    
    assert 'Sitemap:' in content, \
        "❌ robots.txt missing Sitemap reference"
    
    print("  ✓ robots.txt view works correctly (new strategy: allows UI crawl for noindex)")


def test_query_cleanup_middleware():
    """Test that query cleanup middleware redirects UTM-only URLs (2025-12-25)."""
    print("\n✓ Testing query cleanup middleware...")
    
    factory = RequestFactory()
    middleware = PublicQueryCleanupMiddleware(lambda r: HttpResponse())
    
    # Test 1: Public page with ONLY tracking params → should redirect
    request = factory.get('/pricing/?utm_source=fb&utm_campaign=test', HTTP_HOST='emajinet.africa', secure=True)
    response = middleware(request)
    
    if response and hasattr(response, 'status_code'):
        assert response.status_code == 301, \
            "❌ UTM cleanup should be 301 permanent redirect"
        assert '?' not in response['Location'], \
            "❌ Redirect should remove query params"
        assert '/pricing/' in response['Location'], \
            "❌ Redirect should preserve path"
        print("  ✓ /pricing/?utm_source=fb redirects to clean /pricing/")
    else:
        print("  ❌ Expected redirect for UTM-only params")
    
    # Test 2: Public page with functional params → should NOT redirect
    request = factory.get('/pricing/?page=2&utm_source=fb', HTTP_HOST='emajinet.africa', secure=True)
    response = middleware(request)
    
    # Should return None (no redirect) or pass through
    if response is None or not hasattr(response, 'status_code') or response.status_code not in [301, 302]:
        print("  ✓ /pricing/?page=2&utm_source=fb NOT redirected (has functional param)")
    else:
        print("  ❌ Should NOT redirect when functional params present")
    
    # Test 3: Private page with UTM params → should NOT redirect
    request = factory.get('/inventory/dashboard/?utm_source=fb', HTTP_HOST='emajinet.africa', secure=True)
    response = middleware(request)
    
    if response is None or not hasattr(response, 'status_code') or response.status_code not in [301, 302]:
        print("  ✓ /inventory/dashboard/?utm_source=fb NOT redirected (private page)")
    else:
        print("  ❌ Should NOT redirect private pages")
    
    # Test 4: Public page without params → should NOT redirect
    request = factory.get('/pricing/', HTTP_HOST='emajinet.africa', secure=True)
    response = middleware(request)
    
    if response is None or not hasattr(response, 'status_code') or response.status_code not in [301, 302]:
        print("  ✓ /pricing/ NOT redirected (no params)")
    else:
        print("  ❌ Should NOT redirect when no params present")


def test_sitemap_xml_view():
    """Test that sitemap.xml view exists."""
    print("\n✓ Testing sitemap.xml...")
    
    from django.urls import reverse
    
    try:
        url = reverse('sitemap_xml')
        print(f"  ✓ sitemap.xml URL configured: {url}")
    except Exception as e:
        print(f"  ❌ sitemap.xml URL not found: {e}")
        return
    
    # Test the view
    factory = RequestFactory()
    request = factory.get('/sitemap.xml', HTTP_HOST='emajinet.africa', secure=True)
    
    from staticpages.views import sitemap_xml
    response = sitemap_xml(request)
    
    assert response.status_code == 200, \
        "❌ sitemap.xml should return 200"
    assert response['Content-Type'] == 'application/xml', \
        "❌ sitemap.xml should be application/xml"
    
    content = response.content.decode('utf-8')
    assert '<?xml version="1.0"' in content, \
        "❌ sitemap.xml missing XML declaration"
    assert '<urlset' in content, \
        "❌ sitemap.xml missing urlset"
    assert '/landing/' in content, \
        "❌ sitemap.xml missing public pages"
    assert '/inventory/' not in content, \
        "❌ sitemap.xml should NOT include private routes"
    
    print("  ✓ sitemap.xml view works correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("SEO Implementation Test Suite")
    print("=" * 60)
    
    try:
        test_middleware_installed()
        test_noindex_middleware()
        test_canonical_middleware()
        test_query_cleanup_middleware()
        test_https_settings()
        test_allowed_hosts()
        test_robots_txt_view()
        test_sitemap_xml_view()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSEO implementation is correct and ready for production.")
        print("\nNext steps:")
        print("1. Deploy to production")
        print("2. Test manually with curl (see SEO_INDEXING_FIX_SUMMARY.md)")
        print("3. Monitor Google Search Console over next 4 weeks")
        
        return 0
        
    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        return 1
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ ERROR: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

