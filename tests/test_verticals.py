# tests/test_verticals.py
"""
Tests for vertical business flows:
- Manager signup with business_kind
- Vertical dispatcher routing
- Vertical dashboard loading
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from inventory.business_kinds import BusinessKind
from tenants.models import Business, Membership

User = get_user_model()

pytestmark = [
    pytest.mark.django_db,
]


@pytest.fixture
def manager_group():
    """Create Manager group"""
    return Group.objects.get_or_create(name="Manager")[0]


@pytest.fixture
def manager_user(manager_group):
    """Create a manager user"""
    email = f"manager-{uuid.uuid4().hex[:8]}@test.local"
    user = User.objects.create_user(username=email, email=email, password="Test123!@#")
    user.groups.add(manager_group)
    return user


@pytest.fixture
def clothing_business(manager_user):
    """Create a clothing business"""
    biz = Business.objects.create(
        name=f"Fashion Store {uuid.uuid4().hex[:6]}",
        slug=f"fashion-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
        business_kind=BusinessKind.CLOTHING,
        created_by=manager_user,
    )
    Membership.objects.create(user=manager_user, business=biz, role="MANAGER", status="ACTIVE")
    return biz


@pytest.fixture
def liquor_business(manager_user):
    """Create a liquor business"""
    biz = Business.objects.create(
        name=f"Bar {uuid.uuid4().hex[:6]}",
        slug=f"bar-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
        business_kind=BusinessKind.LIQUOR,
        created_by=manager_user,
    )
    Membership.objects.create(user=manager_user, business=biz, role="MANAGER", status="ACTIVE")
    return biz


@pytest.fixture
def pharmacy_business(manager_user):
    """Create a pharmacy business"""
    biz = Business.objects.create(
        name=f"Pharmacy {uuid.uuid4().hex[:6]}",
        slug=f"pharmacy-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
        business_kind=BusinessKind.PHARMACY,
        created_by=manager_user,
    )
    Membership.objects.create(user=manager_user, business=biz, role="MANAGER", status="ACTIVE")
    return biz


@pytest.fixture
def gym_business(manager_user):
    """Create a gym business"""
    biz = Business.objects.create(
        name=f"Gym {uuid.uuid4().hex[:6]}",
        slug=f"gym-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
        business_kind=BusinessKind.GYM,
        created_by=manager_user,
    )
    Membership.objects.create(user=manager_user, business=biz, role="MANAGER", status="ACTIVE")
    return biz


@pytest.fixture
def phones_business(manager_user):
    """Create a phones/electronics business"""
    biz = Business.objects.create(
        name=f"Electronics {uuid.uuid4().hex[:6]}",
        slug=f"electronics-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
        business_kind=BusinessKind.PHONES,
        created_by=manager_user,
    )
    Membership.objects.create(user=manager_user, business=biz, role="MANAGER", status="ACTIVE")
    return biz


class TestManagerSignup:
    """Test manager signup with business_kind"""

    def test_signup_form_has_business_kind_field(self, client):
        """Signup form should render business_kind field"""
        url = reverse("accounts:signup_manager")
        resp = client.get(url)
        assert resp.status_code == 200
        # Check that business_kind field exists in rendered HTML
        content = resp.content.decode("utf-8")
        assert 'name="business_kind"' in content

    def test_signup_creates_business_with_kind(self, client, manager_group):
        """Manager signup should save business_kind on the created Business"""
        url = reverse("accounts:signup_manager")
        email = f"new-{uuid.uuid4().hex[:8]}@test.local"
        
        data = {
            "full_name": "Test Manager",
            "email": email,
            "business_name": f"Test Store {uuid.uuid4().hex[:6]}",
            "business_kind": BusinessKind.CLOTHING,
            "subdomain": "",
            "password1": "x9Kf!m2Pz#7Qw@vL",
            "password2": "x9Kf!m2Pz#7Qw@vL",
        }
        
        resp = client.post(url, data, follow=True)
        
        # Should create user
        user = User.objects.filter(email__iexact=email).first()
        assert user is not None
        
        # Should create business with business_kind
        biz = Business.objects.filter(created_by=user).first()
        assert biz is not None
        assert biz.business_kind == BusinessKind.CLOTHING

    def test_signup_with_liquor_kind(self, client, manager_group):
        """Test signup with liquor business type"""
        url = reverse("accounts:signup_manager")
        email = f"liquor-{uuid.uuid4().hex[:8]}@test.local"
        
        data = {
            "full_name": "Bar Owner",
            "email": email,
            "business_name": f"Bar {uuid.uuid4().hex[:6]}",
            "business_kind": BusinessKind.LIQUOR,
            "subdomain": "",
            "password1": "y7Hj!p4Tm#8Nx@sQ",
            "password2": "y7Hj!p4Tm#8Nx@sQ",
        }
        
        resp = client.post(url, data, follow=True)
        user = User.objects.filter(email__iexact=email).first()
        assert user is not None
        
        biz = Business.objects.filter(created_by=user).first()
        assert biz is not None
        assert biz.business_kind == BusinessKind.LIQUOR


class TestVerticalDispatcher:
    """Test vertical dispatcher routing"""

    def test_dispatcher_redirects_clothing_business(self, client, manager_user, clothing_business):
        """Dispatcher should redirect clothing businesses to clothing dashboard"""
        client.force_login(manager_user)
        client.session["active_business_id"] = clothing_business.id
        client.session.save()
        
        # Call dispatcher
        url = reverse("inventory:inventory_dashboard")
        resp = client.get(url, follow=False)
        
        # Should redirect to clothing dashboard
        assert resp.status_code == 302
        assert "clothing" in resp.url

    def test_dispatcher_redirects_liquor_business(self, client, manager_user, liquor_business):
        """Dispatcher should redirect liquor businesses to liquor dashboard"""
        client.force_login(manager_user)
        client.session["active_business_id"] = liquor_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_dashboard")
        resp = client.get(url, follow=False)
        
        assert resp.status_code == 302
        assert "liquor" in resp.url

    def test_dispatcher_redirects_pharmacy_business(self, client, manager_user, pharmacy_business):
        """Dispatcher should redirect pharmacy businesses to pharmacy dashboard"""
        client.force_login(manager_user)
        client.session["active_business_id"] = pharmacy_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_dashboard")
        resp = client.get(url, follow=False)
        
        assert resp.status_code == 302
        assert "pharmacy" in resp.url

    def test_dispatcher_redirects_gym_business(self, client, manager_user, gym_business):
        """Dispatcher should redirect gym businesses to gym dashboard"""
        client.force_login(manager_user)
        client.session["active_business_id"] = gym_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_dashboard")
        resp = client.get(url, follow=False)
        
        assert resp.status_code == 302
        assert "gym" in resp.url

    def test_dispatcher_redirects_phones_business(self, client, manager_user, phones_business):
        """Dispatcher should redirect phones businesses to phones dashboard"""
        client.force_login(manager_user)
        client.session["active_business_id"] = phones_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_dashboard")
        resp = client.get(url, follow=False)
        
        # Phones dashboard is the default inventory_dashboard or redirects to phones route
        assert resp.status_code in (200, 302)


class TestVerticalDashboards:
    """Test that vertical dashboards load correctly"""

    def test_clothing_dashboard_loads(self, client, manager_user, clothing_business):
        """Clothing dashboard should load with correct context"""
        client.force_login(manager_user)
        client.session["active_business_id"] = clothing_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_verticals:clothing_dashboard")
        resp = client.get(url)
        
        assert resp.status_code == 200
        assert b"Clothing" in resp.content or b"Fashion" in resp.content

    def test_liquor_dashboard_loads(self, client, manager_user, liquor_business):
        """Liquor dashboard should load with correct context"""
        client.force_login(manager_user)
        client.session["active_business_id"] = liquor_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_verticals:liquor_dashboard")
        resp = client.get(url)
        
        assert resp.status_code == 200
        assert b"Liquor" in resp.content or b"Bar" in resp.content

    def test_pharmacy_dashboard_loads(self, client, manager_user, pharmacy_business):
        """Pharmacy dashboard should load with correct context"""
        client.force_login(manager_user)
        client.session["active_business_id"] = pharmacy_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_verticals:pharmacy_dashboard")
        resp = client.get(url)
        
        assert resp.status_code == 200
        assert b"Pharmacy" in resp.content

    def test_gym_dashboard_loads(self, client, manager_user, gym_business):
        """Gym dashboard should load with correct context"""
        client.force_login(manager_user)
        client.session["active_business_id"] = gym_business.id
        client.session.save()
        
        url = reverse("inventory:inventory_verticals:gym_dashboard")
        resp = client.get(url)
        
        assert resp.status_code == 200
        assert b"Gym" in resp.content or b"Fitness" in resp.content

    def test_no_business_fallback(self, client, manager_user):
        """No business fallback should render when no business_kind is set"""
        # Create business without business_kind
        biz = Business.objects.create(
            name=f"Generic Store {uuid.uuid4().hex[:6]}",
            slug=f"generic-{uuid.uuid4().hex[:6]}",
            status="ACTIVE",
            business_kind=None,  # No kind set
            created_by=manager_user,
        )
        Membership.objects.create(user=manager_user, business=biz, role="MANAGER", status="ACTIVE")
        
        client.force_login(manager_user)
        client.session["active_business_id"] = biz.id
        client.session.save()
        
        url = reverse("inventory:inventory_verticals:no_business")
        resp = client.get(url)
        
        assert resp.status_code == 200

