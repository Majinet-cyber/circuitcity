# tenant_smoke.py
# Quick ad-hoc smoke test for tenant activation + isolation.
# Recommended run (PowerShell):
#   python manage.py shell -c "import runpy; runpy.run_path('tenant_smoke.py')"
#
# Alternative (still works now that we avoid indented with-blocks):
#   Get-Content .\tenant_smoke.py -Raw | python manage.py shell

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.conf import settings
from tenants.models import Business, Membership

# -------------------------- helpers --------------------------
User = get_user_model()

def url_or(name: str, default: str) -> str:
    try:
        return reverse(name)
    except Exception:
        return default

DASH     = url_or("dashboard:home", "/")
ACTIVATE = url_or("tenants:activate_mine", "/tenants/activate/")
CHOOSE   = url_or("tenants:choose_business", "/tenants/choose/")
JOIN     = url_or("tenants:join_as_agent", "/tenants/join/")

def P(ok: bool, msg: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + msg)

# ----------------- make shell-safe overrides -----------------
# 1) allow test host + disable SSL redirect for this ephemeral run
try:
    hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
    for h in ("testserver", "localhost", "127.0.0.1"):
        if h not in hosts:
            hosts.append(h)
    settings.ALLOWED_HOSTS = hosts
    settings.SECURE_SSL_REDIRECT = False
except Exception as e:
    print("WARN: could not set ALLOWED_HOSTS/SECURE_SSL_REDIRECT:", e)

# 2) force plain StaticFilesStorage and patch the module-level instance
#    so {% static %} won’t blow up on a missing favicon.
try:
    settings.STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
    import django.contrib.staticfiles.storage as sf_storage
    sf_storage.staticfiles_storage = sf_storage.StaticFilesStorage()
except Exception as e:
    print("WARN: could not patch staticfiles storage:", e)

# -------------------------- clean slate --------------------------
User.objects.filter(username__in=["alice_mgr", "bob_mgr"]).delete()
Business.objects.filter(name__in=["Alpha Phones", "Beta Phones"]).delete()

# -------------------- create actors & tenants --------------------
alice = User.objects.create_user("alice_mgr", password="x12345!")
bob   = User.objects.create_user("bob_mgr",   password="x12345!")
alpha = Business.objects.create(name="Alpha Phones", slug="alpha-phones", status="ACTIVE", created_by=alice)
beta  = Business.objects.create(name="Beta Phones",  slug="beta-phones",  status="ACTIVE", created_by=bob)

Membership.objects.create(user=alice, business=alpha, role="MANAGER", status="ACTIVE")
Membership.objects.create(user=bob,   business=beta,  role="MANAGER", status="ACTIVE")

# ---------------- Alice flow: activate & guard -------------------
c = Client(); c.force_login(alice)
r = c.get(ACTIVATE, follow=True)

sid = c.session.get("active_business_id") or c.session.get("biz_id")
P(sid == alpha.id, f"Alice session targets Alpha (got {sid}, expect {alpha.id})")

chain_urls = [u for (u, _code) in getattr(r, "redirect_chain", [])]
not_joined = all("/tenants/join" not in u for u in chain_urls)
P(not_joined, "Alice NOT pushed to Join-as-agent")

# Cross-tenant switch should be blocked
c.post(CHOOSE, {"business_id": beta.id}, follow=True)
sid2 = c.session.get("active_business_id") or c.session.get("biz_id")
P(sid2 == alpha.id, "Alice cannot switch to Beta")

# ---------------- Bob flow: isolation ---------------------------
c.logout()
c2 = Client(); c2.force_login(bob)
r2 = c2.get(ACTIVATE, follow=True)
sid_b = c2.session.get("active_business_id") or c2.session.get("biz_id")
P(sid_b == beta.id, f"Bob session targets Beta (got {sid_b}, expect {beta.id})")
P(sid_b != alpha.id, "Bob did not inherit Alice's tenant")

# With active biz, a manager should NOT be redirected to create/join pages
r_home = c2.get(DASH, follow=True)
chain_urls2 = [u for (u, _code) in getattr(r_home, "redirect_chain", [])]
ok = all(p not in chain_urls2 for p in [ACTIVATE, CHOOSE, JOIN])
P(ok, "Manager with active biz is NOT redirected to create/join")

print("\nDone.")
