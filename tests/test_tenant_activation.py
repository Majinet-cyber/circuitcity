# tests/test_tenant_activation.py
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse, NoReverseMatch
from django.test.utils import override_settings

from tenants.models import Business, Membership


def url_or(name: str, default: str) -> str:
    """Best-effort reverse; fall back to a literal path if the URL name isn't registered."""
    try:
        return reverse(name)
    except NoReverseMatch:
        return default


DASH     = url_or("dashboard:home", "/")
ACTIVATE = url_or("tenants:activate_mine", "/tenants/activate/")
CHOOSE   = url_or("tenants:choose_business", "/tenants/choose/")
JOIN     = url_or("tenants:join_as_agent", "/tenants/join/")

User = get_user_model()


def _paths(chain):
    """Extract just the URLs from Django test client's redirect_chain for easy messages."""
    return [u for (u, _code) in chain or []]


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "localhost", "127.0.0.1"],
    SECURE_SSL_REDIRECT=False,
    # Use plain storage so templates referencing e.g. favicon.ico don't require a manifest during tests
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
)
@pytest.mark.django_db
def test_tenant_activation_and_isolation():
    # Create managers & businesses
    alice = User.objects.create_user("alice_mgr", password="x12345!")
    bob   = User.objects.create_user("bob_mgr",   password="x12345!")

    alpha = Business.objects.create(
        name="Alpha Phones", slug="alpha-phones", status="ACTIVE", created_by=alice
    )
    beta = Business.objects.create(
        name="Beta Phones", slug="beta-phones", status="ACTIVE", created_by=bob
    )

    Membership.objects.create(user=alice, business=alpha, role="MANAGER", status="ACTIVE")
    Membership.objects.create(user=bob,   business=beta,  role="MANAGER", status="ACTIVE")

    # --- Alice flow ---
    c = Client()
    c.force_login(alice)

    r = c.get(ACTIVATE, follow=True)
    sid = c.session.get("active_business_id") or c.session.get("biz_id")
    assert sid == alpha.id, f"Alice session should target Alpha (got {sid}, expect {alpha.id})"

    chain_urls = _paths(getattr(r, "redirect_chain", []))
    assert all("/tenants/join" not in u for u in chain_urls), (
        "Alice must NOT be pushed to join; chain was: " + " -> ".join(chain_urls)
    )

    # Cross-tenant switch should be blocked
    c.post(CHOOSE, {"business_id": beta.id}, follow=True)
    sid2 = c.session.get("active_business_id") or c.session.get("biz_id")
    assert sid2 == alpha.id, "Alice cannot switch to Beta"

    # --- Bob flow ---
    c.logout()
    c2 = Client()
    c2.force_login(bob)

    r2 = c2.get(ACTIVATE, follow=True)
    sid_b = c2.session.get("active_business_id") or c2.session.get("biz_id")
    assert sid_b == beta.id, f"Bob session should target Beta (got {sid_b}, expect {beta.id})"
    assert sid_b != alpha.id, "Bob must not inherit Alice's tenant"

    # With active biz, Bob shouldn’t be redirected to create/join
    r_home = c2.get(DASH, follow=True)
    chain_urls2 = _paths(getattr(r_home, "redirect_chain", []))
    for p in (ACTIVATE, CHOOSE, JOIN):
        assert p not in chain_urls2, f"Unexpected redirect to {p}; chain: {' -> '.join(chain_urls2)}"
