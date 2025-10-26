# cc/helpers/nav.py
from django.urls import reverse

def nav_items(user):
    # single source of truth for labels, icons, urls
    items = [
        {"key":"dashboard","label":"Dashboard","icon":"i-cc i-dashboard-green","url":reverse("hq:home"), "perm": "hq.view_dashboard"},
        {"key":"subscriptions","label":"Subscriptions","icon":"i-cc i-subscriptions-green","url":reverse("hq:subscriptions"), "perm":"billing.view_subscription"},
        {"key":"invoices","label":"Invoices","icon":"i-cc i-invoices-green","url":reverse("hq:invoices"), "perm":"billing.view_invoice"},
        {"key":"businesses","label":"Businesses","icon":"i-cc i-businesses-green","url":reverse("hq:business_list"), "perm":"tenants.view_business"},
        {"key":"agents","label":"Agents","icon":"i-cc i-agents-green","url":reverse("hq:agents"), "perm":"agents.view_agent"},
        {"key":"wallet","label":"Wallet","icon":"i-cc i-wallet-green","url":reverse("hq:wallet"), "perm":"wallet.view_wallet"},
        {"key":"stock","label":"Stock trends","icon":"i-cc i-stock-green","url":reverse("hq:stock_trends"), "perm":"inventory.view_inventory"},
    ]
    # superusers see all; else check perms
    if user.is_superuser:
        return items
    allowed = []
    for it in items:
        if it["perm"] is None or user.has_perm(it["perm"]):
            allowed.append(it)
    return allowed


