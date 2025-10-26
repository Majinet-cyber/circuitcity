import pytest
from django.urls import reverse
from django.contrib.auth.models import Group, User
from tenants.models import Business
from inventory.models import InventoryItem
from audit.models import AuditLog

@pytest.fixture
def biz_a(db): return Business.objects.create(name="A Store")
@pytest.fixture
def biz_b(db): return Business.objects.create(name="B Store")

@pytest.fixture
def manager(db, biz_a):
    g,_ = Group.objects.get_or_create(name="Manager")
    u = User.objects.create_user("mgr", password="x")
    u.groups.add(g)
    # not staff!
    assert not u.is_staff
    return u

@pytest.fixture
def client_as_manager(client, manager, biz_a):
    client.login(username="mgr", password="x")
    session = client.session
    session["active_business_id"] = biz_a.id
    session.save()
    return client

def test_manager_cannot_access_admin(client_as_manager, settings):
    resp = client_as_manager.get("/" + getattr(settings, "ADMIN_URL", "__admin__/"))
    assert resp.status_code in (302, 403, 404)

def test_tenant_isolation_read(db, client_as_manager, biz_a, biz_b):
    a = InventoryItem.objects.create(business=biz_a)
    b = InventoryItem.objects.create(business=biz_b)
    resp = client_as_manager.get(reverse("inventory:stock_list"))
    # Template renders 'a' but must not render 'b'
    assert str(a.pk) in resp.content.decode()
    assert str(b.pk) not in resp.content.decode()

def test_crud_and_audit(db, client_as_manager):
    # create
    resp = client_as_manager.post(reverse("inventory:scan_in"), {
        "imei": "123",
        "product": 1, "location": 1, "order_price": 1000, "received_date": "2025-01-01",
    })
    assert resp.status_code in (302, 200)
    item = InventoryItem.objects.latest("id")
    # restore
    item.is_active = False; item.save()
    r2 = client_as_manager.post(reverse("inventory:restore", args=[item.pk]))
    assert r2.status_code in (302, 200)
    assert AuditLog.objects.filter(entity_id=str(item.pk)).exists()



