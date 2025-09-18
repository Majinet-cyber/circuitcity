# inventory/urls.py
from . import api_super
urlpatterns += [
    path("api/super/rebalance/", api_super.rebalancing_suggestions, name="super_rebalance_api"),
    path("api/super/deadstock/", api_super.deadstock_catalog,      name="super_deadstock_api"),
]
