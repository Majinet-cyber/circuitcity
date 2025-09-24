import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_pages_load_with_session_defaults(client, django_user_model):
    u = django_user_model.objects.create_user("t","t@e.com","x")
    client.login(username="t", password="x")
    s = client.session
    s["active_business_id"] = 1
    s["active_location_id"] = 1
    s.save()
    for name in ["inventory:scan_in","inventory:scan_sold","inventory:stock_list"]:
        r = client.get(reverse(name))
        assert r.status_code in (200, 302)
