import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_login_page(client):
    r = client.get(reverse("accounts:login"))
    assert r.status_code == 200
    assert "Sign in" in r.content.decode()

@pytest.mark.django_db
def test_signup_manager_page(client):
    r = client.get(reverse("accounts:signup_manager"))
    assert r.status_code == 200
    # Render without touching QueryDict from the template
    assert "Create your store" in r.content.decode()

@pytest.mark.django_db
def test_inventory_pages_render(client, django_user_model):
    u = django_user_model.objects.create_user("x@x.com", "x@x.com", "password12345")
    client.post(reverse("accounts:login"), {"identifier":"x@x.com","password":"password12345"})
    for name in ["inventory:inventory_dashboard", "inventory:stock_list"]:
        r = client.get(reverse(name))
        assert r.status_code == 200
