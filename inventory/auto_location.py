# inventory/auto_location.py
from django.apps import apps
from django.db.models.signals import post_save
from django.dispatch import receiver

def register():
    """
    Hook up a post_save signal on the Business/Store model to ensure each new
    store has at least one Location with the store's name.
    """
    Business = apps.get_model("tenants", "Business")  # adjust app/model if different
    Location = apps.get_model("inventory", "Location")

    # If either model isn't present, just bail (keeps this module safe to import)
    if Business is None or Location is None:
        return

    # Figure out the FK field name from Location -> Business (if present)
    loc_business_field = None
    for f in Location._meta.get_fields():
        try:
            if getattr(f, "is_relation", False) and getattr(f, "many_to_one", False):
                if getattr(getattr(f, "remote_field", None), "model", None) is Business:
                    loc_business_field = f.name
                    break
        except Exception:
            pass

    @receiver(post_save, sender=Business, dispatch_uid="inventory.ensure_default_location_for_business")
    def ensure_default_location_for_business(sender, instance, created, **kwargs):
        if not created:
            return

        # Work out a nice display name
        store_name = (
            getattr(instance, "display_name", None)
            or getattr(instance, "name", None)
            or getattr(instance, "title", None)
            or "Main"
        )

        # Build a queryset scoped to this business (if FK exists)
        qs = Location.objects.all()
        create_kwargs = {"name": store_name}
        if loc_business_field:
            qs = qs.filter(**{f"{loc_business_field}_id": instance.pk})
            create_kwargs[loc_business_field] = instance

        # If this store already has a location, do nothing
        if qs.exists():
            return

        # Optional flags if your model has them
        if hasattr(Location, "is_default"):
            create_kwargs["is_default"] = True
        if hasattr(Location, "is_active"):
            create_kwargs["is_active"] = True

        Location.objects.create(**create_kwargs)


