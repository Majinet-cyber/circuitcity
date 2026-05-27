# tests/test_bug_monitor.py
"""
Bug Monitor test suite — covers all 15 required tests plus helpers.

Test framework: pytest + pytest-django (as used by the project).
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("admin_su", "admin@example.com", "pass1234")


@pytest.fixture
def staff_user(db):
    return User.objects.create_user("staff1", "staff@example.com", "pass1234", is_staff=True)


@pytest.fixture
def plain_user(db):
    return User.objects.create_user("plain1", "plain@example.com", "pass1234")


@pytest.fixture
def factory():
    return RequestFactory()


def _make_request(factory, user=None, path="/some/view/", method="GET", post_data=None):
    """Build a minimal fake request for middleware testing."""
    if method == "POST":
        req = factory.post(path, data=post_data or {})
    else:
        req = factory.get(path)
    req.user = user or type("AnonymousUser", (), {"is_authenticated": False, "pk": None})()
    req.session = {}
    req.META["REMOTE_ADDR"] = "127.0.0.1"
    req.META["HTTP_USER_AGENT"] = "pytest/1.0"
    return req


def _trigger_middleware(request, exc):
    """Run BugCaptureMiddleware.process_exception and return None (it always returns None)."""
    from hq.middleware import BugCaptureMiddleware

    def get_response(r):
        return None

    mw = BugCaptureMiddleware(get_response)
    return mw.process_exception(request, exc)


# ===========================================================================
# TEST 1: 500 error creates a SystemIssue
# ===========================================================================

@pytest.mark.django_db
def test_500_creates_system_issue(factory, plain_user):
    from hq.models_bugmonitor import SystemIssue

    req = _make_request(factory, user=plain_user, path="/crash/")
    exc = RuntimeError("Something broke badly")

    initial_count = SystemIssue.objects.count()
    _trigger_middleware(req, exc)
    assert SystemIssue.objects.count() == initial_count + 1

    issue = SystemIssue.objects.latest("created_at")
    assert issue.error_type == "RuntimeError"
    assert "Something broke badly" in issue.message
    assert issue.status_code == 500


# ===========================================================================
# TEST 2: Repeated same error increments recurrence count
# ===========================================================================

@pytest.mark.django_db
def test_repeated_error_increments_occurrence_count(factory):
    from hq.models_bugmonitor import SystemIssue

    req = _make_request(factory, path="/repeated/error/")
    exc = ValueError("Repeated failure")

    _trigger_middleware(req, exc)
    _trigger_middleware(req, exc)
    _trigger_middleware(req, exc)

    issues = SystemIssue.objects.filter(error_type="ValueError", path="/repeated/error/")
    assert issues.count() == 1, "Same fingerprint should produce one row"
    assert issues.first().occurrence_count == 3


# ===========================================================================
# TEST 3: SystemIssueOccurrence is created for each hit
# ===========================================================================

@pytest.mark.django_db
def test_occurrence_created_per_hit(factory):
    from hq.models_bugmonitor import SystemIssue, SystemIssueOccurrence

    req = _make_request(factory, path="/occurrence-test/")
    exc = KeyError("missing key")

    _trigger_middleware(req, exc)
    _trigger_middleware(req, exc)

    issue = SystemIssue.objects.filter(error_type="KeyError").first()
    assert issue is not None
    assert SystemIssueOccurrence.objects.filter(issue=issue).count() == 2


# ===========================================================================
# TEST 4: Sensitive fields are sanitized (general)
# ===========================================================================

@pytest.mark.django_db
def test_sanitize_dict_redacts_sensitive_keys():
    from hq.sanitizer import sanitize_dict

    data = {
        "username": "alice",
        "password": "supersecret",
        "token": "abcdef123",
        "otp": "123456",
        "note": "hello",
    }
    result = sanitize_dict(data)

    assert result["username"] == "alice"
    assert result["note"] == "hello"
    assert result["password"] == "[REDACTED]"
    assert result["token"] == "[REDACTED]"
    assert result["otp"] == "[REDACTED]"


# ===========================================================================
# TEST 5: Password/token/otp/cookie/authorization fields NOT stored
# ===========================================================================

@pytest.mark.django_db
def test_sensitive_fields_not_stored_in_occurrence(factory):
    """Verify the stored sanitized_post_data never contains raw sensitive values."""
    from hq.models_bugmonitor import SystemIssue

    req = factory.post(
        "/login/",
        data={
            "username": "alice",
            "password": "mysupersecretpassword",
            "csrfmiddlewaretoken": "tok123",
        },
    )
    req.user = type("anon", (), {"is_authenticated": False, "pk": None})()
    req.session = {}
    req.META["REMOTE_ADDR"] = "127.0.0.1"

    exc = Exception("Login exploded")
    _trigger_middleware(req, exc)

    issue = SystemIssue.objects.filter(path="/login/").first()
    assert issue is not None

    # Raw sensitive values must not appear in the stored JSON
    stored_post = str(issue.sanitized_post_data)
    assert "mysupersecretpassword" not in stored_post
    assert "tok123" not in stored_post
    assert "alice" in stored_post  # non-sensitive field preserved


# ===========================================================================
# TEST 6: Cleared issue can be marked cleared with cleared_by and cleared_at
# ===========================================================================

@pytest.mark.django_db
def test_mark_cleared(superuser):
    from hq.models_bugmonitor import SystemIssue, IssueStatus

    issue = SystemIssue.objects.create(
        fingerprint="test-fp-clear-001",
        title="Test issue",
        status=IssueStatus.NEW,
    )

    issue.mark_cleared(actor=superuser, notes="Fixed in deploy v2.1")

    issue.refresh_from_db()
    assert issue.status == IssueStatus.CLEARED
    assert issue.cleared_by == superuser
    assert issue.cleared_at is not None
    assert "Fixed in deploy v2.1" in issue.resolution_notes


# ===========================================================================
# TEST 7: Recurring error after cleared reopens as NEW
# ===========================================================================

@pytest.mark.django_db
def test_cleared_issue_reopens_on_recurrence(factory, superuser):
    from hq.models_bugmonitor import SystemIssue, IssueStatus

    req = _make_request(factory, path="/reopen-test/")
    exc = OverflowError("Math overflow")

    # First hit → creates issue
    _trigger_middleware(req, exc)
    issue = SystemIssue.objects.filter(error_type="OverflowError").first()
    assert issue is not None

    # Clear it
    issue.mark_cleared(actor=superuser)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.CLEARED

    # Same error recurs → issue should reopen
    _trigger_middleware(req, exc)
    issue.refresh_from_db()
    assert issue.status == IssueStatus.NEW
    assert issue.occurrence_count == 2


# ===========================================================================
# TEST 8: Non-admin cannot access HQ Bug Monitor
# ===========================================================================

@pytest.mark.django_db
def test_non_admin_cannot_access_bug_monitor(client, plain_user):
    client.force_login(plain_user)
    response = client.get("/hq/bugs/")
    # Should be 403 (not admin) or redirect to login
    assert response.status_code in (403, 302)


# ===========================================================================
# TEST 9: Admin with permission CAN access Bug Monitor
# ===========================================================================

@pytest.mark.django_db
def test_admin_can_access_bug_monitor(client, superuser):
    client.force_login(superuser)
    response = client.get("/hq/bugs/")
    assert response.status_code == 200


# ===========================================================================
# TEST 10: Stack trace hidden without can_view_stack_traces
# ===========================================================================

@pytest.mark.django_db
def test_stack_trace_hidden_without_permission(client, staff_user):
    from hq.models_bugmonitor import SystemIssue, IssueStatus

    # staff_user is in platform_admin group so they pass hq_admin_required
    from django.contrib.auth.models import Group
    grp, _ = Group.objects.get_or_create(name="platform_admin")
    staff_user.groups.add(grp)

    issue = SystemIssue.objects.create(
        fingerprint="fp-stack-hidden",
        title="Stack test",
        stack_trace="Traceback (most recent call last):\n  File ...\nValueError: test",
        status=IssueStatus.NEW,
    )

    client.force_login(staff_user)
    # staff_user does NOT have can_view_stack_traces
    response = client.get(f"/hq/bugs/{issue.pk}/")
    assert response.status_code == 200
    content = response.content.decode()
    # Stack trace section should show "restricted" warning but NOT the trace content
    # when user lacks permission
    assert "can_view_stack_traces" in content or "hidden" in content.lower() or "restricted" in content.lower()
    # The actual traceback text should NOT appear
    assert "Traceback (most recent call last)" not in content


# ===========================================================================
# TEST 11: Stack trace visible with can_view_stack_traces permission
# ===========================================================================

@pytest.mark.django_db
def test_stack_trace_visible_with_permission(client, superuser):
    from hq.models_bugmonitor import SystemIssue, IssueStatus

    issue = SystemIssue.objects.create(
        fingerprint="fp-stack-visible",
        title="Stack visible test",
        stack_trace="Traceback (most recent call last):\n  File 'views.py'\nRuntimeError: boom",
        status=IssueStatus.NEW,
    )

    client.force_login(superuser)
    response = client.get(f"/hq/bugs/{issue.pk}/")
    assert response.status_code == 200
    content = response.content.decode()
    # Superuser can see stack trace
    assert "Traceback (most recent call last)" in content


# ===========================================================================
# TEST 12: Audit log created when bug is cleared
# ===========================================================================

@pytest.mark.django_db
def test_audit_log_created_on_clear(client, superuser):
    from hq.models_bugmonitor import SystemIssue, AdminAuditLog, IssueStatus

    issue = SystemIssue.objects.create(
        fingerprint="fp-audit-clear",
        title="Audit clear test",
        status=IssueStatus.INVESTIGATING,
    )

    client.force_login(superuser)
    response = client.post(
        f"/hq/bugs/{issue.pk}/action/",
        data={"action": "mark_cleared", "resolution_notes": "Fixed."},
    )
    assert response.status_code in (200, 302)

    entry = AdminAuditLog.objects.filter(action="bug_cleared", target_id=str(issue.pk)).first()
    assert entry is not None
    assert entry.actor == superuser


# ===========================================================================
# TEST 13: Audit log created when bug is assigned
# ===========================================================================

@pytest.mark.django_db
def test_audit_log_created_on_assign(client, superuser, staff_user):
    from hq.models_bugmonitor import SystemIssue, AdminAuditLog, IssueStatus

    issue = SystemIssue.objects.create(
        fingerprint="fp-audit-assign",
        title="Audit assign test",
        status=IssueStatus.NEW,
    )

    client.force_login(superuser)
    response = client.post(
        f"/hq/bugs/{issue.pk}/action/",
        data={"action": "assign", "assignee_id": str(staff_user.pk)},
    )
    assert response.status_code in (200, 302)

    entry = AdminAuditLog.objects.filter(action="bug_assigned", target_id=str(issue.pk)).first()
    assert entry is not None
    assert entry.actor == superuser


# ===========================================================================
# TEST 14: Audit log created when admin role/group changes
# ===========================================================================

@pytest.mark.django_db
def test_audit_log_created_on_role_change(client, superuser, staff_user):
    from django.contrib.auth.models import Group
    from hq.models_bugmonitor import AdminAuditLog

    grp, _ = Group.objects.get_or_create(name="Bug Monitor Admin")

    client.force_login(superuser)
    response = client.post(
        f"/hq/accounts/{staff_user.pk}/groups/",
        data={"groups": [str(grp.pk)]},
    )
    assert response.status_code in (200, 302)

    entry = AdminAuditLog.objects.filter(
        action="admin_role_changed", target_id=str(staff_user.pk)
    ).first()
    assert entry is not None
    assert entry.actor == superuser
    assert "Bug Monitor Admin" in str(entry.after)


# ===========================================================================
# TEST 15: Existing tests still pass (smoke check on imports)
# ===========================================================================

def test_no_import_regressions():
    """Verify key modules still import cleanly after our additions."""
    import hq.models
    import hq.middleware
    import hq.sanitizer
    import hq.permissions
    import hq.admin
    import hq.views_bugmonitor
    import hq.views_accounts

    # Verify models are importable and have expected attributes
    from hq.models_bugmonitor import SystemIssue, SystemIssueOccurrence, AdminAuditLog
    assert hasattr(SystemIssue, "build_fingerprint")
    assert hasattr(SystemIssue, "mark_cleared")
    assert hasattr(AdminAuditLog, "record")


# ===========================================================================
# Extra: Sanitizer edge cases
# ===========================================================================

def test_sanitizer_nested_dict():
    from hq.sanitizer import sanitize_dict

    data = {
        "user": {
            "name": "Bob",
            "password": "shouldberedacted",
            "prefs": {"theme": "dark", "api_key": "1234"},
        }
    }
    result = sanitize_dict(data)
    assert result["user"]["name"] == "Bob"
    assert result["user"]["password"] == "[REDACTED]"
    assert result["user"]["prefs"]["theme"] == "dark"
    assert result["user"]["prefs"]["api_key"] == "[REDACTED]"


def test_sanitizer_empty_input():
    from hq.sanitizer import sanitize_dict, sanitize_querydict
    assert sanitize_dict(None) == {}
    assert sanitize_dict({}) == {}
    assert sanitize_querydict(None) == {}


def test_fingerprint_stability():
    from hq.models_bugmonitor import SystemIssue

    fp1 = SystemIssue.build_fingerprint("ValueError", 500, "/api/items/", "api:items", "File views.py")
    fp2 = SystemIssue.build_fingerprint("ValueError", 500, "/api/items/", "api:items", "File views.py")
    assert fp1 == fp2


def test_fingerprint_normalizes_numeric_ids():
    from hq.models_bugmonitor import SystemIssue

    fp_a = SystemIssue.build_fingerprint("ValueError", 500, "/items/123/", "items:detail", "")
    fp_b = SystemIssue.build_fingerprint("ValueError", 500, "/items/456/", "items:detail", "")
    assert fp_a == fp_b, "Numeric path segments should normalize to same fingerprint"


def test_middleware_never_raises(factory):
    """Middleware should silently absorb any internal error."""
    from hq.middleware import BugCaptureMiddleware

    def get_response(r):
        return None

    mw = BugCaptureMiddleware(get_response)

    req = factory.get("/test/")
    req.user = None  # Intentionally broken user object
    req.META["REMOTE_ADDR"] = "127.0.0.1"

    # Should not raise, ever
    result = mw.process_exception(req, RuntimeError("bad"))
    assert result is None
