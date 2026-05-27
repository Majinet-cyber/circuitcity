# tests/test_tenants.py
import importlib
import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import NoReverseMatch, reverse

# -----------------------
# Optional dependencies
# -----------------------
try:
    from audit.models import AuditLog  # optional app
    AUDIT_AVAILABLE = True
except Exception:
    AuditLog = None  # type: ignore
    AUDIT_AVAILABLE = False

# Optional models used by CRUD route
inv_models = importlib.import_module("inventory.models")
Product = getattr(inv_models, "Product", None)
InventoryItem = getattr(inv_models, "InventoryItem", None)

ten_models = importlib.import_module("tenants.models")
Business = getattr(ten_models, "Business", None)
Location = getattr(ten_models, "Location", None)
Membership = getattr(ten_models, "Membership", None)

User = get_user_model()


def url_or(name: str, default: str | None = None) -> str | None:
    """Reverse a URL name or fall back to a default literal (or None)."""
    try:
        return reverse(name)
    except NoReverseMatch:
        return default


DASH      = url_or("dashboard:home", "/")
STOCKLIST = url_or("inventory:stock_list", "/inventory/stock/")
SCAN_IN   = url_or("inventory:scan_in", None)  # if missing, we skip CRUD test
RESTORE   = url_or("inventory:restore", None)  # expects pk in args

# Make staticfiles simple in tests to avoid manifest errors (favicon, etc.)
pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("simpler_static_settings"),
]


@pytest.fixture(scope="module")
def simpler_static_settings(request):
    """Relax staticfiles + SSL redirect during tests (module scope)."""
    # NOTE: using Django's override_settings decorator can be done per-test too.
    old_ssl = getattr(settings, "SECURE_SSL_REDIRECT", False)
    old_storage = getattr(settings, "STATICFILES_STORAGE", "")
    settings.SECURE_SSL_REDIRECT = False
    settings.STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
    yield
    settings.SECURE_SSL_REDIRECT = old_ssl
    settings.STATICFILES_STORAGE = old_storage


@pytest.fixture
def biz_a():
    if Business is None:
        pytest.skip("tenants.Business not available")
    return Business.objects.create(name="A Store", slug=f"a-store-{uuid.uuid4().hex[:6]}", status="ACTIVE")


@pytest.fixture
def biz_b():
    if Business is None:
        pytest.skip("tenants.Business not available")
    return Business.objects.create(name="B Store", slug=f"b-store-{uuid.uuid4().hex[:6]}", status="ACTIVE")


@pytest.fixture
def manager(biz_a):
    # Create a non-staff user who belongs to "Manager" group
    g, _ = Group.objects.get_or_create(name="Manager")
    u = User.objects.create_user("mgr", password="x")
    u.groups.add(g)
    assert not getattr(u, "is_staff", False)
    if Membership is not None:
        Membership.objects.get_or_create(user=u, business=biz_a, defaults={"role": "MANAGER", "status": "ACTIVE"})
    return u


@pytest.fixture
def client_as_manager(client, manager, biz_a):
    # Log in and set the tenant in session
    client.login(username="mgr", password="x")
    session = client.session
    session["active_business_id"] = biz_a.id
    session.save()
    return client


def test_manager_cannot_access_admin(client_as_manager):
    admin_path = getattr(settings, "ADMIN_URL", "__admin__/")
    # Ensure it looks like a URL path
    if not admin_path.startswith("/"):
        admin_path = "/" + admin_path
    resp = client_as_manager.get(admin_path)
    # Depending on how admin is wired, this might be 302 (to login), 403, or 404.
    assert resp.status_code in (302, 403, 404)


@pytest.mark.skipif(InventoryItem is None, reason="InventoryItem model not available")
def test_tenant_isolation_read(client_as_manager, biz_a, biz_b):
    # Create minimal stock rows per business (assumes InventoryItem accepts 'business' only;
    # if your model needs more fields, extend as needed.)
    if Product is None:
        pytest.skip("Product model not available")

    prod_a = Product.objects.create(code=f"A-{uuid.uuid4().hex[:6]}", model="ModelA")
    prod_b = Product.objects.create(code=f"B-{uuid.uuid4().hex[:6]}", model="ModelB")

    a = InventoryItem.objects.create(business=biz_a, product=prod_a)
    b = InventoryItem.objects.create(business=biz_b, product=prod_b)

    if STOCKLIST is None:
        pytest.skip("inventory:stock_list route is not available")

    resp = client_as_manager.get(f"{STOCKLIST}?format=json")
    data = resp.json()
    row_ids = {row.get("id") for row in data.get("data", [])}

    # Page should contain only the item from the active business (biz_a)
    assert a.pk in row_ids
    assert b.pk not in row_ids


@pytest.mark.skipif(not AUDIT_AVAILABLE, reason="audit app not installed")
def test_crud_and_audit(client_as_manager, biz_a):
    """
    Exercise a minimal create + restore flow and assert an audit row is written.
    Skips automatically if:
      - scan_in / restore routes are missing
      - Product / Location models don't exist (and are required by your view)
    """
    if SCAN_IN is None or RESTORE is None:
        pytest.skip("inventory scan_in/restore routes are not available")

    # If your scan_in view expects Product/Location, create minimal ones:
    data = {
        "imei": "123",
        "order_price": 1000,
        "received_date": "2025-01-01",
    }

    # product
    if Product is not None:
        prod = Product.objects.create(name="Test Phone", business=biz_a)
        data["product"] = prod.pk
    else:
        # Only include 'product' if your view requires it. If it's strictly required
        # and the model doesn't exist, skip this test gracefully.
        pass

    # location
    if Location is not None:
        loc = Location.objects.create(name="HQ", business=biz_a)
        data["location"] = loc.pk

    # --- create (scan in) ---
    resp = client_as_manager.post(SCAN_IN, data)
    assert resp.status_code in (200, 302)

    # Grab latest item
    assert InventoryItem is not None
    item = InventoryItem.objects.latest("id")

    # --- restore ---
    restore_url = RESTORE
    # RESTORE may be a named URL requiring args; prefer reverse with args if available
    try:
        restore_url = reverse("inventory:restore", args=[item.pk])
    except NoReverseMatch:
        # fall back to literal RESTORE if it already contains the right pattern
        if "%s" in (RESTORE or ""):
            restore_url = (RESTORE or "").replace("%s", str(item.pk))
        elif RESTORE and RESTORE.endswith("/"):
            restore_url = f"{RESTORE}{item.pk}/"

    r2 = client_as_manager.post(restore_url)
    assert r2.status_code in (200, 302)

    # --- audit written ---
    assert AuditLog.objects.filter(entity_id=str(item.pk)).exists()


def test_manager_agents_page_loads(client_as_manager, biz_a):
    """
    Regression test: Ensure /tenants/manager/agents/ loads without 500 error.
    Verifies the agent_detail URL name is correctly namespaced.
    """
    try:
        url = reverse("tenants:manager_review_agents")
    except NoReverseMatch:
        pytest.skip("tenants:manager_review_agents route not available")
    
    resp = client_as_manager.get(url)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    
    # Verify page contains "Agents" or similar text
    content = resp.content.decode("utf-8")
    assert "agent" in content.lower() or "team" in content.lower(), "Expected agents-related content"


def test_agent_detail_url_reversal(manager, biz_a):
    """
    Regression test: Ensure tenants:agent_detail URL can be reversed.
    This was broken when template used 'inventory:agent_detail' instead.
    """
    try:
        url = reverse("tenants:agent_detail", args=[manager.id])
    except NoReverseMatch as e:
        pytest.fail(f"tenants:agent_detail URL not found: {e}")
    
    assert url, "URL should not be empty"
    assert str(manager.id) in url, f"URL should contain agent ID {manager.id}"
    # Expected pattern: /tenants/agents/<agent_id>/
    assert "/agents/" in url, "URL should contain /agents/ path segment"


def test_agent_detail_page_loads(client_as_manager, biz_a):
    """
    Regression test: Ensure agent detail page loads for valid agent.
    """
    # Create an agent user
    if Membership is None:
        pytest.skip("Membership model not available")
    
    # Create a location for the agent (required by validation)
    location = None
    if Location is not None:
        location = Location.objects.create(name="Test Location", business=biz_a)
    
    agent_user = User.objects.create_user("agent1", password="x")
    Membership.objects.create(
        user=agent_user,
        business=biz_a,
        role="AGENT",
        status="ACTIVE",
        location=location
    )
    
    try:
        url = reverse("tenants:agent_detail", args=[agent_user.id])
    except NoReverseMatch:
        pytest.skip("tenants:agent_detail route not available")
    
    resp = client_as_manager.get(url)
    # Should return 200 (success) or 403 (permission denied) or 302 (redirect)
    # but NOT 500 (server error) or 404 with wrong URL
    assert resp.status_code in (200, 302, 403), \
        f"Expected 200/302/403, got {resp.status_code}"
    
    # If successful, verify agent name appears
    if resp.status_code == 200:
        content = resp.content.decode("utf-8")
        assert agent_user.username in content or "agent1" in content.lower()