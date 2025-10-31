import os
from django.apps import apps
from django.db import transaction, models

Item = apps.get_model("inventory","InventoryItem")

biz_id_env = os.environ.get("BIZ_ID")
if not biz_id_env:
    print('ERROR: set BIZ_ID, e.g. $env:BIZ_ID="2"')
    raise SystemExit(2)
biz_id = int(biz_id_env)

with transaction.atomic():
    # 1) Copy from current_location.business where available
    n_copy = (Item._base_manager
              .filter(business__isnull=True, current_location__business__isnull=False)
              .update(business_id=models.F("current_location__business_id")))

    # 2) Anything still NULL -> set to chosen biz
    n_fallback = (Item._base_manager
                  .filter(business__isnull=True)
                  .update(business_id=biz_id))

print("Items backfill complete")
print("copied_from_location:", n_copy)
print("fallback_to_biz:", n_fallback)
print("unscoped_total:", Item._base_manager.count())
