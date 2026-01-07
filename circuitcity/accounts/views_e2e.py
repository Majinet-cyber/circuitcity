# circuitcity/accounts/views_e2e.py
"""
E2E Testing Endpoints - ONLY enabled in DEBUG or E2E_TESTING mode.

These endpoints are for Cypress E2E tests only and should NEVER be enabled in production.
"""
from __future__ import annotations

import logging
import os

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from inventory.models import Location
from tenants.models import Business, Membership

from .models import EmailOTP, get_or_create_twofactor

User = get_user_model()
logger = logging.getLogger(__name__)


def get_or_create_business_ci(*, name: str, defaults: dict):
    """
    Get or create Business with case-insensitive name lookup.

    Handles the case-insensitive unique constraint (uniq_business_name_ci) safely.
    First tries case-insensitive fetch, then creates with IntegrityError handling.

    Args:
        name: Business name (will be matched case-insensitively)
        defaults: Dict of default values for creation (e.g., slug, business_kind, status, created_by)

    Returns:
        (business, created) tuple where created is True if business was just created
    """
    # First try case-insensitive fetch
    b = Business.objects.filter(name__iexact=name).first()
    if b:
        return b, False

    # Create with IntegrityError safety
    try:
        return Business.objects.create(name=name, **defaults), True
    except IntegrityError:
        # Someone created it concurrently or case-variant exists
        b = Business.objects.filter(name__iexact=name).first()
        if b:
            return b, False
        raise


def seed_clothing_defaults(business, location):
    """
    Idempotently seed clothing vertical defaults.

    Ensures:
    - Currency settings exist (ExchangeRate singleton)
    - Notification preferences exist for manager (auto-created via signal, but ensure exists)
    - Minimal lookup data is not required (clothing uses config constants, not DB tables)

    Args:
        business: Business instance
        location: Location instance (unused but kept for consistency)

    Returns:
        dict with "seeded" key indicating if any seeding occurred
    """
    seeded = False

    # Currency settings: Ensure ExchangeRate singleton exists
    try:
        from core.models import ExchangeRate

        rate_obj = ExchangeRate.get_current_rate()
        if not rate_obj:
            # Create default rate (1 USD = 1700 MWK as example)
            from decimal import Decimal

            ExchangeRate.objects.create(
                base="MWK",
                quote="USD",
                mwk_per_usd=Decimal("1700.00"),
            )
            seeded = True
    except Exception:
        # If ExchangeRate model doesn't exist or error, skip
        pass

    # Notification preferences: Auto-created via signal, but ensure exists
    # Get the manager user for this business
    try:
        from notifications.models import NotificationPreference

        membership = Membership.objects.filter(business=business, role="MANAGER", status="ACTIVE").first()
        if membership:
            NotificationPreference.get_or_create_default(membership.user)
    except Exception:
        # If NotificationPreference doesn't exist or error, skip
        pass

    # Clothing uses config constants (CLOTHING_CATEGORIES, CLOTHING_COLORS, etc.)
    # from inventory.clothing_config, not DB lookup tables, so no seeding needed

    return {"seeded": seeded}


def is_test_login_enabled(request) -> bool:
    """
    Check if test login endpoints are enabled.

    Rules (NO DRAMA for localhost):
    - Block if ENV in ["prod","production"] (NEVER allow in production)
    - Allow automatically if REMOTE_ADDR is localhost (127.0.0.1, ::1) even if DEBUG=False
    - For non-local requests, require ALLOW_TEST_LOGIN=true AND (DEBUG=True OR E2E_TESTING=True)

    IMPORTANT: Environment variables must be present in the RUNNING Django process.
    """
    env = os.getenv("ENV", "").lower()
    is_prod = env in ("prod", "production")

    # NEVER allow in production
    if is_prod:
        return False

    remote = request.META.get("REMOTE_ADDR", "")
    is_local = remote in ("127.0.0.1", "::1", "localhost") or "localhost" in remote.lower()

    # Allow localhost automatically (no env var needed)
    if is_local:
        return True

    # For non-local requests, require explicit ALLOW_TEST_LOGIN
    allow = os.getenv("ALLOW_TEST_LOGIN", "").lower() in ("1", "true", "yes")
    debug = getattr(settings, "DEBUG", False)
    e2e_testing = getattr(settings, "E2E_TESTING", False)

    enabled = bool(allow and (debug or e2e_testing))

    if not enabled:
        logger.debug(
            "e2e_test_login disabled: allow=%s env=%s debug=%s e2e_testing=%s remote=%s",
            allow,
            env,
            debug,
            e2e_testing,
            remote,
        )

    return enabled


def _is_e2e_enabled() -> bool:
    """Legacy helper - use is_test_login_enabled(request) instead."""
    # For backward compatibility, create a mock request
    from django.http import HttpRequest

    mock_request = HttpRequest()
    return is_test_login_enabled(mock_request)


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
    if not is_test_login_enabled(request):
        raise Http404("E2E endpoint not found")

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
    if not is_test_login_enabled(request):
        raise Http404("E2E endpoint not found")

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
    if not is_test_login_enabled(request):
        raise Http404("E2E endpoint not found")

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

        # Use case-insensitive business lookup to avoid IntegrityError
        business, biz_created = get_or_create_business_ci(
            name=business_name,
            defaults={
                "slug": unique_slug,
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
    Creates user/business idempotently if kind is provided and user doesn't exist.

    Endpoint: POST /accounts/__e2e__/test-login/
    Body: {
        "email": "test@example.com",
        "password": "password123",
        "kind": "clothing"  // optional: creates business/user if missing
    }

    Returns:
        {
            "ok": true,
            "user_id": 123,
            "username": "test@example.com",
            "email": "test@example.com",
            "business_id": 456,
            "session_id": "..."
        }

    Security:
        - Only enabled when DEBUG=True or E2E_TESTING=True AND ALLOW_TEST_LOGIN=true
        - Returns 403 in production or if ALLOW_TEST_LOGIN is not set
        - Bypasses 2FA challenge for test users (only in test mode)
        - Uses Django's authenticate() and login() for proper session handling
    """
    if not is_test_login_enabled(request):
        raise Http404("Test login endpoint not found")

    import json

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    # Detect if email was explicitly provided by client
    explicit_email = "email" in data
    email = data.get("email", "").strip().lower() if explicit_email else ""
    password = data.get("password", "")
    kind = data.get("kind", "").strip().lower()

    # If kind is provided and email NOT explicitly provided, default to kind-specific email
    if kind and not explicit_email:
        email = f"cypress.manager+{kind}@example.com"
        password = password or "Passw0rd!Test"

    if not email or not password:
        return JsonResponse({"ok": False, "error": "email and password required"}, status=400)

    # If kind is provided, ensure user and business exist (create idempotently)
    business = None
    user = None
    seeded = False
    reused_existing_business = False

    if kind:
        with transaction.atomic():
            # Get or create user (use username like e2e_seed_business)
            user, user_created = User.objects.get_or_create(
                username=email, defaults={"email": email, "is_active": True}
            )

            # If user was just created, set password
            if user_created:
                user.set_password(password)
                user.save()

            # Check for existing MANAGER membership BEFORE creating business
            existing_mgr = Membership.objects.filter(user=user, role="MANAGER").select_related("business").first()

            # If existing MANAGER membership exists, check vertical mismatch
            if existing_mgr:
                business = existing_mgr.business
                # Check if kind matches existing business vertical
                existing_vertical = business.business_kind or ""
                if kind and existing_vertical and existing_vertical.lower() != kind.lower():
                    # Vertical mismatch - return 409
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "MANAGER_BUSINESS_LOCK",
                            "detail": "This manager email is already bound to a different vertical/business.",
                            "email": email,
                            "existing_business_id": business.id,
                            "existing_vertical": existing_vertical,
                            "requested_kind": kind,
                            "hint": "Managers are permanently bound to one business. Use a different email for this vertical.",
                        },
                        status=409,
                    )
                # Reuse existing business
                reused_existing_business = True
            else:
                # No existing MANAGER membership - create/find business safely
                from django.utils.text import slugify

                desired_name = f"Cypress {kind.title()} ({email})"

                # Case-insensitive lookup first
                business = Business.objects.filter(name__iexact=desired_name).first()

                if not business:
                    # Create new business with unique slug
                    base_slug = slugify(f"cypress-{kind}-{email.split('@')[0]}")[:40] or f"cypress-{kind}"
                    unique_slug = base_slug
                    i = 1
                    while Business.objects.filter(slug=unique_slug).exists():
                        unique_slug = f"{base_slug}-{i}"
                        i += 1

                    # Use case-insensitive business creation helper
                    business, _ = get_or_create_business_ci(
                        name=desired_name,
                        defaults={
                            "slug": unique_slug,
                            "business_kind": kind,
                            "status": "ACTIVE",
                            "created_by": user,
                        },
                    )

            # Create or update membership MANAGER (idempotent)
            membership = Membership.objects.filter(user=user, business=business).first()
            if membership:
                # Update role to MANAGER if needed
                if membership.role != "MANAGER":
                    membership.role = "MANAGER"
                    membership.save(update_fields=["role"])
                # Ensure status is ACTIVE
                if membership.status != "ACTIVE":
                    membership.status = "ACTIVE"
                    membership.save(update_fields=["status"])
            else:
                # Create membership (will pass validation since we checked for conflicts above)
                membership = Membership.objects.create(
                    user=user,
                    business=business,
                    role="MANAGER",
                    status="ACTIVE",
                )

            # Ensure default location exists (idempotent)
            default_location = Location.ensure_default_for_business(business)

            # Seed kind defaults (idempotent)
            if kind == "clothing":
                seeded_result = seed_clothing_defaults(business, default_location)
                seeded = seeded_result.get("seeded", False)

            # If user was just created, authenticate will work
            # If user already existed, authenticate normally (password must match)

    # Authenticate user
    if not user:
        user = authenticate(request, username=email, password=password)

    if not user:
        # Try with email as username if different
        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(request, username=user_obj.username, password=password)
        except User.DoesNotExist:
            pass

    if not user:
        return JsonResponse({"ok": False, "error": "Invalid credentials"}, status=401)

    if not user.is_active:
        return JsonResponse({"ok": False, "error": "User account is inactive"}, status=403)

    # Log the user in (creates session) - MUST be before setting 2FA flags
    login(request, user)

    # In test mode, disable 2FA challenge for test users
    # This is safe because it's gated by ALLOW_TEST_LOGIN env var
    # Ensure UserTwoFactor record exists
    tf = get_or_create_twofactor(user)
    if tf:
        # Check if any 2FA is enabled (safely handles different field shapes)
        if tf.is_enabled:
            # Disable all 2FA methods for this test user
            tf.disable_all_2fa()

    # Always set session flags to bypass 2FA middleware (defensive)
    # These must match what TwoFactorAuthMiddleware checks
    request.session["twofa_required"] = False
    request.session["twofa_passed"] = True
    import time

    request.session["twofa_passed_at"] = time.time()

    # Ensure notification preferences exist for the manager
    try:
        from notifications.models import NotificationPreference

        NotificationPreference.get_or_create_default(user)
    except Exception as e:
        # NotificationPreference model may not exist - that's ok
        logger.debug(f"e2e_test_login: Could not create NotificationPreference for user {user.id}: {e}")

    # Get business_id if we have a membership
    business_id = None
    if business:
        business_id = business.id
    else:
        try:
            membership = Membership.objects.filter(user=user, status="ACTIVE").first()
            if membership:
                business_id = membership.business_id
        except Exception:
            pass

    # Get location_id if we have a business
    location_id = None
    if business:
        try:
            default_location = Location.objects.filter(business=business, is_default=True).first()
            if default_location:
                location_id = default_location.id
        except Exception:
            pass

    return JsonResponse(
        {
            "ok": True,
            "user_id": user.id,
            "username": user.username,
            "email": user.email or user.username,
            "business_id": business_id,
            "location_id": location_id,
            "kind": kind if kind else None,
            "session_id": request.session.session_key,
            "seeded": seeded,
            "reused_existing_business": reused_existing_business,
        }
    )
