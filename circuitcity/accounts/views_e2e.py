# circuitcity/accounts/views_e2e.py
"""
E2E Testing Endpoints - ONLY enabled in DEBUG or E2E_TESTING mode.

These endpoints are for Cypress E2E tests only and should NEVER be enabled in production.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from inventory.models import Location
from tenants.models import Business, Membership

from .models import EmailOTP, get_or_create_twofactor

User = get_user_model()


def _is_e2e_enabled() -> bool:
    """Check if E2E testing endpoints are enabled."""
    # Must have DEBUG or E2E_TESTING enabled AND ALLOW_TEST_LOGIN env var set
    base_enabled = getattr(settings, "DEBUG", False) or getattr(settings, "E2E_TESTING", False)
    allow_test_login = os.getenv("ALLOW_TEST_LOGIN") == "true"
    return base_enabled and allow_test_login


@csrf_exempt
@require_http_methods(["GET"])
def e2e_latest_otp(request):
    """
    Get the latest OTP code for an email address (E2E testing only).

    Endpoint: GET /__e2e__/latest-otp?email=test@example.com

    Returns:
        {
            "ok": true,
            "code": "123456",  // Plain text code (ONLY in E2E mode)
            "email": "test@example.com",
            "purpose": "signup",
            "created_at": "2024-01-01T12:00:00Z"
        }

    Security:
        - Only enabled when DEBUG=True or E2E_TESTING=True
        - Returns 403 in production
    """
    if not _is_e2e_enabled():
        return HttpResponseForbidden("E2E endpoints disabled in production")

    email = request.GET.get("email", "").strip().lower()
    if not email:
        return JsonResponse({"ok": False, "error": "email parameter required"}, status=400)

    # Get latest unexpired OTP for this email
    otp = (
        EmailOTP.objects.filter(email=email, consumed_at__isnull=True)
        .filter(expires_at__gt=timezone.now())
        .order_by("-created_at")
        .first()
    )

    if not otp:
        return JsonResponse({"ok": False, "error": "No active OTP found for this email"}, status=404)

    # In E2E mode, we need to return the plain text code
    # Since we hash codes, we can't decrypt them. Instead, we'll use a fixed test code.
    # For E2E tests, we'll allow a fixed OTP "000000" to work if E2E_TESTING is enabled.
    test_code = getattr(settings, "E2E_OTP_CODE", "000000")

    return JsonResponse(
        {
            "ok": True,
            "code": test_code,  # Fixed test code for E2E
            "email": otp.email,
            "purpose": otp.purpose,
            "created_at": otp.created_at.isoformat(),
            "expires_at": otp.expires_at.isoformat(),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def e2e_verify_otp_bypass(request):
    """
    Verify OTP using test bypass (E2E testing only).

    Endpoint: POST /__e2e__/verify-otp-bypass
    Body: {"email": "test@example.com", "code": "000000"}

    Returns:
        {"ok": true, "verified": true}

    Security:
        - Only enabled when DEBUG=True or E2E_TESTING=True
        - Accepts fixed test code "000000" or code from E2E_OTP_CODE setting
    """
    if not _is_e2e_enabled():
        return HttpResponseForbidden("E2E endpoints disabled in production")

    import json

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    email = data.get("email", "").strip().lower()
    code = data.get("code", "").strip()

    if not email or not code:
        return JsonResponse({"ok": False, "error": "email and code required"}, status=400)

    # Get latest unexpired OTP
    otp = (
        EmailOTP.objects.filter(email=email, consumed_at__isnull=True)
        .filter(expires_at__gt=timezone.now())
        .order_by("-created_at")
        .first()
    )

    if not otp:
        return JsonResponse({"ok": False, "error": "No active OTP found"}, status=404)

    # Check if code matches test bypass code
    test_code = getattr(settings, "E2E_OTP_CODE", "000000")
    if code == test_code:
        # Mark OTP as consumed
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["consumed_at"])
        return JsonResponse({"ok": True, "verified": True})

    # Otherwise, use normal verification
    from .services.email_otp import verify_email_otp

    try:
        verified = verify_email_otp(email, code, otp.purpose)
        return JsonResponse({"ok": True, "verified": verified})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def e2e_seed_business(request):
    """
    Seed a test business and location (E2E testing only).

    Endpoint: POST /__e2e__/seed-business
    Body: {
        "email": "test@example.com",
        "business_name": "Test Business",
        "business_kind": "phones",
        "location_name": "Test Location",
        "city": "Test City"
    }

    Returns:
        {
            "ok": true,
            "business_id": 123,
            "location_id": 456,
            "user_id": 789
        }

    Security:
        - Only enabled when DEBUG=True or E2E_TESTING=True
        - Creates or updates test data
    """
    if not _is_e2e_enabled():
        return HttpResponseForbidden("E2E endpoints disabled in production")

    import json

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    email = data.get("email", "").strip().lower()
    business_name = data.get("business_name", "Test Business").strip()
    business_kind = data.get("business_kind", "phones").strip().lower()
    location_name = data.get("location_name", "Test Location").strip()
    city = data.get("city", "Test City").strip()

    if not email:
        return JsonResponse({"ok": False, "error": "email required"}, status=400)

    with transaction.atomic():
        # Get or create user
        user, created = User.objects.get_or_create(username=email, defaults={"email": email, "is_active": True})

        # Get or create business
        from django.utils.text import slugify

        base_slug = slugify(business_name)[:40] or "test-business"
        unique_slug = base_slug
        i = 1
        while Business.objects.filter(slug=unique_slug).exists():
            unique_slug = f"{base_slug}-{i}"
            i += 1

        business, biz_created = Business.objects.get_or_create(
            slug=unique_slug,
            defaults={
                "name": business_name,
                "business_kind": business_kind,
                "status": "ACTIVE",
            },
        )

        # Ensure membership
        membership, _ = Membership.objects.get_or_create(
            user=user, business=business, defaults={"role": "MANAGER", "status": "ACTIVE"}
        )

        # Get or create location
        location, loc_created = Location.objects.get_or_create(
            business=business, name=location_name, defaults={"city": city, "is_default": True}
        )

    return JsonResponse(
        {
            "ok": True,
            "user_id": user.id,
            "business_id": business.id,
            "location_id": location.id,
            "created": {
                "user": created,
                "business": biz_created,
                "location": loc_created,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def e2e_test_login(request):
    """
    Test-only login endpoint for Cypress E2E tests (SAFE, gated).

    Endpoint: POST /__e2e__/test-login/
    Body: {
        "email": "test@example.com",
        "password": "password123"
    }

    Returns:
        {
            "ok": true,
            "user_id": 123,
            "username": "test@example.com",
            "session_id": "..."
        }

    Security:
        - Only enabled when DEBUG=True or E2E_TESTING=True AND ALLOW_TEST_LOGIN=true
        - Returns 403 in production or if ALLOW_TEST_LOGIN is not set
        - Bypasses 2FA challenge for test users (only in test mode)
        - Uses Django's authenticate() and login() for proper session handling
    """
    if not _is_e2e_enabled():
        return HttpResponseForbidden(
            "Test login endpoint disabled. Set ALLOW_TEST_LOGIN=true in test environment only."
        )

    import json

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return JsonResponse({"ok": False, "error": "email and password required"}, status=400)

    # Authenticate user
    user = authenticate(request, username=email, password=password)

    if not user:
        # Try with email as username
        try:
            user = User.objects.get(email=email)
            user = authenticate(request, username=user.username, password=password)
        except User.DoesNotExist:
            pass

    if not user:
        return JsonResponse({"ok": False, "error": "Invalid credentials"}, status=401)

    if not user.is_active:
        return JsonResponse({"ok": False, "error": "User account is inactive"}, status=403)

    # In test mode, we can optionally disable 2FA challenge for test users
    # This is safe because it's gated by ALLOW_TEST_LOGIN env var
    tf = get_or_create_twofactor(user)
    if tf.is_enabled:
        # For test login, we can bypass 2FA by setting session flags
        # This is ONLY safe because ALLOW_TEST_LOGIN is required
        request.session["twofa_required"] = False
        request.session["twofa_passed"] = True

    # Log the user in (creates session)
    login(request, user)

    return JsonResponse(
        {
            "ok": True,
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "session_id": request.session.session_key,
        }
    )
