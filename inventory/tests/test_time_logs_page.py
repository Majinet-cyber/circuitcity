"""
Test suite for the Time Logs page (/inventory/time/logs/).

Ensures the view:
- Actually renders HTML (not a wrapper object debug message)
- Returns status 200 for logged-in users with business context
- Contains expected page elements
"""
import pytest
import json
from datetime import datetime, time, timedelta
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from tenants.models import Business, Membership
from inventory.models import Location
from inventory.models_attendance import TimeLog
from inventory.business_kinds import BusinessKind

User = get_user_model()


@pytest.mark.django_db
def test_time_logs_page_renders_successfully(client):
    """
    Test that the time logs page renders properly and returns valid HTML.

    This test specifically addresses the bug where the page was returning:
    "_wrapped: callable returned by view (not executed)"

    Now it should return proper HTML with status 200.
    """
    # Create user
    user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    # Create business
    business = Business.objects.create(
        name="Test Phone Business", slug="test-phone-business", business_kind=BusinessKind.PHONES
    )

    # Create membership
    Membership.objects.create(business=business, user=user, role="MANAGER", status="ACTIVE")

    # Get or create location (Business creation may auto-create a default location)
    location = Location.objects.filter(business=business).first()
    if not location:
        location = Location.objects.create(business=business, name="Main Store", is_default=True)

    # Login
    client.login(username="testuser", password="testpass123")

    # Set up session with business context (required by @require_business decorator in urls.py)
    session = client.session
    session["active_business_id"] = business.id
    session.save()

    # Perform GET request
    url = reverse("inventory:time_logs")
    response = client.get(url)

    # Assert successful response
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Assert it's not the wrapper object debug text
    content = response.content.decode("utf-8")
    assert (
        "_wrapped: callable returned by view" not in content
    ), "Page still returning wrapper object instead of rendering"
    assert "not executed" not in content, "Page still showing 'not executed' debug message"

    # Assert the page contains expected elements
    assert "Time Logs" in content, "Page title 'Time Logs' not found"

    # Check template name if available (HttpResponse might not have it, but TemplateResponse does)
    if hasattr(response, "template_name"):
        assert "time_logs.html" in str(response.template_name), "Wrong template used"


@pytest.mark.django_db
def test_time_logs_page_without_business_context(client):
    """
    Test that the page handles missing business context gracefully.

    With @require_business in urls.py, it should redirect to business selection.
    """
    # Create and login user (but don't create business/membership)
    user = User.objects.create_user(username="testuser2", email="test2@example.com", password="testpass123")
    client.login(username="testuser2", password="testpass123")

    # No business context in session
    url = reverse("inventory:time_logs")
    response = client.get(url)

    # Should redirect (302) when no business context due to @require_business
    assert response.status_code == 302, f"Expected 302 redirect when no business context, got {response.status_code}"

    # Should redirect to tenants activation or settings
    assert (
        "tenants" in response.url.lower() or "settings" in response.url.lower() or "activate" in response.url.lower()
    ), f"Expected redirect to tenants/settings/activate, got {response.url}"


@pytest.mark.django_db
def test_time_logs_page_requires_login(client):
    """
    Test that unauthenticated users cannot access the time logs page.
    """
    url = reverse("inventory:time_logs")
    response = client.get(url)

    # Should redirect to login (302) for unauthenticated users
    assert response.status_code == 302, f"Expected redirect for unauthenticated user, got {response.status_code}"

    # The app may redirect to tenants page, login, or accounts - all valid for unauthenticated users
    # Just verify it redirects somewhere (not rendering the page itself)
    assert response.url is not None, "Should redirect somewhere, not render the page"


@pytest.mark.django_db
def test_time_logs_page_content_structure(client):
    """
    Test that the time logs page contains expected UI elements.
    """
    # Create user
    user = User.objects.create_user(username="testuser3", email="test3@example.com", password="testpass123")

    # Create business
    business = Business.objects.create(
        name="Test Business 3", slug="test-business-3", business_kind=BusinessKind.PHONES
    )

    # Create membership
    Membership.objects.create(business=business, user=user, role="MANAGER", status="ACTIVE")

    # Login
    client.login(username="testuser3", password="testpass123")

    # Set up session
    session = client.session
    session["active_business_id"] = business.id
    session.save()

    # Get the page
    url = reverse("inventory:time_logs")
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # Check for expected elements from the template
    # The template should have table structure, filters, etc.
    assert "Time Logs" in content, "Missing page title"

    # The template uses JavaScript to load data, so we just check structure exists
    # Not checking for actual log data since that requires database setup


def _login_with_business(client, user, business):
    client.login(username=user.username, password="testpass123")
    session = client.session
    session["active_business_id"] = business.id
    session.save()


def _local_dt(hour, minute=0):
    today = timezone.localdate()
    return timezone.make_aware(datetime.combine(today, time(hour, minute)), timezone.get_current_timezone())


def _post_attendance(client, action, **payload):
    return client.post(
        reverse("inventory:time_attendance_action"),
        data=json.dumps({"action": action, **payload}),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_time_logs_page_renders_manager_dashboard_sections(client):
    manager = User.objects.create_user(username="time_manager", password="testpass123")
    staff = User.objects.create_user(username="time_staff", email="time_staff@example.com", password="testpass123")
    business = Business.objects.create(name="Time Logs Biz", slug="time-logs-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=manager, role="MANAGER", status="ACTIVE")
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")

    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=_local_dt(8, 20))
    TimeLog.objects.create(business=business, user=staff, kind="DEPARTURE", ts=_local_dt(12, 0))

    _login_with_business(client, manager, business)
    response = client.get(reverse("inventory:time_logs"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Present Today" in content
    assert "Late Today" in content
    assert "Active Shifts" in content
    assert "No Checkout" in content
    assert "Staff Attendance Summary" in content
    assert "Raw Event Logs / Audit Trail" in content
    assert "Check In" in content
    assert "GPS/Zone" in content
    assert "Check In" in content or "Check Out" in content


@pytest.mark.django_db
def test_time_logs_api_returns_attendance_summary_and_no_gps(client):
    manager = User.objects.create_user(username="time_manager_api", password="testpass123")
    staff = User.objects.create_user(username="time_staff_api", email="staffapi@example.com", password="testpass123")
    business = Business.objects.create(name="Time Logs API Biz", slug="time-logs-api-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=manager, role="MANAGER", status="ACTIVE")
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")

    start = _local_dt(8, 20)
    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=start)
    TimeLog.objects.create(business=business, user=staff, kind="DEPARTURE", ts=start + timedelta(hours=3))

    _login_with_business(client, manager, business)
    response = client.get(reverse("inventory:time_logs_api"), {"day": timezone.localdate().isoformat()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["kpis"]["present_today"] == 1
    assert payload["kpis"]["late_today"] == 1
    assert payload["attendance_rows"][0]["gps_zone"] == "No GPS"
    assert payload["attendance_rows"][0]["status"] == "Checked Out"


@pytest.mark.django_db
def test_staff_time_logs_api_is_scoped_to_own_attendance(client):
    staff = User.objects.create_user(username="own_time_staff", password="testpass123")
    other = User.objects.create_user(username="other_time_staff", password="testpass123")
    business = Business.objects.create(name="Scoped Time Biz", slug="scoped-time-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    Membership.objects.create(business=business, user=other, role="AGENT", status="ACTIVE")

    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=_local_dt(8, 0))
    TimeLog.objects.create(business=business, user=other, kind="ARRIVAL", ts=_local_dt(8, 0))

    _login_with_business(client, staff, business)
    response = client.get(reverse("inventory:time_logs_api"), {"day": timezone.localdate().isoformat()})

    assert response.status_code == 200
    payload = response.json()
    names = [row["staff"] for row in payload["attendance_rows"]]
    assert names == ["own_time_staff"]
    assert all(log["user"] == "own_time_staff" for log in payload["raw_logs"])


@pytest.mark.django_db
def test_check_in_creates_arrival_with_no_gps_allowed(client):
    staff = User.objects.create_user(username="checkin_staff", password="testpass123")
    business = Business.objects.create(name="Check In Biz", slug="check-in-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")

    _login_with_business(client, staff, business)
    response = _post_attendance(client, "CHECK_IN")

    assert response.status_code == 200
    log = TimeLog.objects.get(user=staff, business=business)
    assert log.kind == "ARRIVAL"
    assert log.geofence_status == "No GPS"
    assert log.lat is None
    assert log.lon is None


@pytest.mark.django_db
def test_check_out_creates_departure_after_active_check_in(client):
    staff = User.objects.create_user(username="checkout_staff", password="testpass123")
    business = Business.objects.create(name="Check Out Biz", slug="check-out-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=_local_dt(8, 0))

    _login_with_business(client, staff, business)
    response = _post_attendance(client, "CHECK_OUT")

    assert response.status_code == 200
    assert TimeLog.objects.filter(user=staff, business=business, kind="DEPARTURE").exists()


@pytest.mark.django_db
def test_duplicate_check_in_is_prevented(client):
    staff = User.objects.create_user(username="duplicate_checkin", password="testpass123")
    business = Business.objects.create(name="Duplicate Biz", slug="duplicate-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=_local_dt(8, 0))

    _login_with_business(client, staff, business)
    response = _post_attendance(client, "CHECK_IN")

    assert response.status_code == 409
    assert response.json()["error"] == "already_checked_in"


@pytest.mark.django_db
def test_checkout_without_check_in_is_prevented(client):
    staff = User.objects.create_user(username="orphan_checkout", password="testpass123")
    business = Business.objects.create(name="Orphan Checkout Biz", slug="orphan-checkout-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")

    _login_with_business(client, staff, business)
    response = _post_attendance(client, "CHECK_OUT")

    assert response.status_code == 409
    assert response.json()["error"] == "not_checked_in"
    assert TimeLog.objects.filter(user=staff, business=business).count() == 0


@pytest.mark.django_db
def test_gps_saved_and_inside_geofence_calculated_from_location(client):
    staff = User.objects.create_user(username="geo_inside_staff", password="testpass123")
    business = Business.objects.create(name="Geo Inside Biz", slug="geo-inside-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True,
        latitude="-13.960000",
        longitude="33.770000",
        geofence_radius_m=200,
    )

    _login_with_business(client, staff, business)
    response = _post_attendance(
        client,
        "CHECK_IN",
        latitude=-13.9601,
        longitude=33.7701,
        accuracy_m=12,
    )

    assert response.status_code == 200
    log = TimeLog.objects.get(user=staff, business=business)
    assert log.accuracy_m == 12
    assert log.distance_m is not None
    assert log.geofence_status == "Inside Zone"


@pytest.mark.django_db
def test_outside_geofence_calculated_from_configured_location(client):
    staff = User.objects.create_user(username="geo_outside_staff", password="testpass123")
    business = Business.objects.create(name="Geo Outside Biz", slug="geo-outside-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True,
        latitude="-13.960000",
        longitude="33.770000",
        geofence_radius_m=50,
    )

    _login_with_business(client, staff, business)
    response = _post_attendance(client, "CHECK_IN", latitude=-13.9700, longitude=33.7800, accuracy_m=20)

    assert response.status_code == 200
    log = TimeLog.objects.get(user=staff, business=business)
    assert log.distance_m and log.distance_m > 50
    assert log.geofence_status == "Outside Zone"


@pytest.mark.django_db
def test_manager_time_logs_api_sees_business_staff(client):
    manager = User.objects.create_user(username="manager_business_logs", password="testpass123")
    staff1 = User.objects.create_user(username="manager_seen_one", password="testpass123")
    staff2 = User.objects.create_user(username="manager_seen_two", password="testpass123")
    business = Business.objects.create(name="Manager Logs Biz", slug="manager-logs-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=manager, role="MANAGER", status="ACTIVE")
    Membership.objects.create(business=business, user=staff1, role="AGENT", status="ACTIVE")
    Membership.objects.create(business=business, user=staff2, role="AGENT", status="ACTIVE")
    TimeLog.objects.create(business=business, user=staff1, kind="ARRIVAL", ts=_local_dt(8, 0))
    TimeLog.objects.create(business=business, user=staff2, kind="ARRIVAL", ts=_local_dt(8, 0))

    _login_with_business(client, manager, business)
    response = client.get(reverse("inventory:time_logs_api"), {"day": timezone.localdate().isoformat()})

    assert response.status_code == 200
    names = {row["staff"] for row in response.json()["attendance_rows"]}
    assert {"manager_seen_one", "manager_seen_two"}.issubset(names)


@pytest.mark.django_db
def test_time_logs_csv_exports_attendance_fields(client):
    manager = User.objects.create_user(username="csv_time_manager", password="testpass123")
    staff = User.objects.create_user(username="csv_time_staff", email="csv@example.com", password="testpass123")
    business = Business.objects.create(name="CSV Time Biz", slug="csv-time-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=manager, role="MANAGER", status="ACTIVE")
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    TimeLog.objects.create(
        business=business,
        user=staff,
        kind="ARRIVAL",
        ts=_local_dt(8, 0),
        accuracy_m=9,
        distance_m=15,
        geofence_status="Inside Zone",
        note="front gate",
    )

    _login_with_business(client, manager, business)
    response = client.get(reverse("inventory:time_logs_export_csv"), {"day": timezone.localdate().isoformat()})
    content = b"".join(response.streaming_content).decode("utf-8")

    assert response.status_code == 200
    assert "accuracy_m,distance_m,geofence,note" in content
    assert "Inside Zone" in content
    assert "front gate" in content


@pytest.mark.django_db
def test_auto_checkout_outside_geofence_creates_departure_once(client):
    staff = User.objects.create_user(username="auto_outside_staff", password="testpass123")
    business = Business.objects.create(name="Auto Outside Biz", slug="auto-outside-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    Location.objects.create(
        business=business,
        name="Main Store",
        is_default=True,
        latitude="-13.960000",
        longitude="33.770000",
        geofence_radius_m=50,
    )
    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=timezone.now() - timedelta(minutes=10))

    _login_with_business(client, staff, business)
    response = _post_attendance(client, "GPS_CHECK", latitude=-13.9700, longitude=33.7800, accuracy_m=10)
    second = _post_attendance(client, "GPS_CHECK", latitude=-13.9700, longitude=33.7800, accuracy_m=10)

    assert response.status_code == 200
    assert response.json()["auto_checked_out"] is True
    assert second.status_code == 200
    assert second.json()["auto_checked_out"] is False
    departures = TimeLog.objects.filter(business=business, user=staff, kind="DEPARTURE")
    assert departures.count() == 1
    assert departures.get().note == "Auto checkout: outside geofence"


@pytest.mark.django_db
def test_gps_check_without_gps_does_not_auto_checkout(client):
    staff = User.objects.create_user(username="gps_denied_staff", password="testpass123")
    business = Business.objects.create(name="GPS Denied Biz", slug="gps-denied-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=timezone.now() - timedelta(minutes=10))

    _login_with_business(client, staff, business)
    response = _post_attendance(client, "GPS_CHECK", gps_denied=True)

    assert response.status_code == 200
    payload = response.json()
    assert payload["auto_checked_out"] is False
    assert payload["warning"] == "Enable location to verify attendance zone."
    assert not TimeLog.objects.filter(business=business, user=staff, kind="DEPARTURE").exists()


@pytest.mark.django_db
def test_worked_duration_counts_while_active_and_idle_does_not_exceed_worked(client):
    staff = User.objects.create_user(username="active_duration_staff", password="testpass123")
    business = Business.objects.create(name="Active Duration Biz", slug="active-duration-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=timezone.now() - timedelta(hours=2))

    _login_with_business(client, staff, business)
    response = client.get(reverse("inventory:time_logs_api"), {"day": timezone.localdate().isoformat()})

    assert response.status_code == 200
    row = response.json()["attendance_rows"][0]
    assert row["status"] == "Active"
    assert row["worked_seconds"] >= 7100
    assert row["idle_seconds"] <= row["worked_seconds"]
    assert response.json()["attendance_status"]["active_work_seconds"] >= 7100


@pytest.mark.django_db
def test_checkout_duration_freezes_after_departure(client):
    staff = User.objects.create_user(username="frozen_duration_staff", password="testpass123")
    business = Business.objects.create(name="Frozen Duration Biz", slug="frozen-duration-biz", business_kind=BusinessKind.PHONES)
    Membership.objects.create(business=business, user=staff, role="AGENT", status="ACTIVE")
    arrival = timezone.now() - timedelta(hours=3)
    departure = arrival + timedelta(hours=1, minutes=30)
    TimeLog.objects.create(business=business, user=staff, kind="ARRIVAL", ts=arrival)
    TimeLog.objects.create(business=business, user=staff, kind="DEPARTURE", ts=departure)

    _login_with_business(client, staff, business)
    response = client.get(reverse("inventory:time_logs_api"), {"day": timezone.localdate().isoformat()})

    assert response.status_code == 200
    row = response.json()["attendance_rows"][0]
    assert row["status"] == "Checked Out"
    assert 5390 <= row["worked_seconds"] <= 5410
    assert response.json()["attendance_status"]["active_work_seconds"] == row["worked_seconds"]
