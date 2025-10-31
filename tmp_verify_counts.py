from django.apps import apps
Item = apps.get_model("inventory","InventoryItem")

print("scoped_count:", Item.objects.count())
print("unscoped_count:", Item._base_manager.count())

last = Item._base_manager.order_by("-id").first()
print("last_id:", getattr(last,"id",None))
print("last_business_id:", getattr(last,"business_id",None))
print("last_imei:", getattr(last,"imei",None))
print("last_status:", getattr(last,"status",None))
