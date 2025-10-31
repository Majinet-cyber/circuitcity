# inventory/perm_utils.py
def is_business_manager(user):
    if not user.is_authenticated: return False
    return (
        user.is_superuser
        or user.groups.filter(name__in=["Business Manager", "Admin"]).exists()
        or user.has_perm("inventory.change_stock")
        or user.has_perm("inventory.delete_stock")
    )
