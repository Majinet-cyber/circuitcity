from accounts.utils import get_tengasale_role


def can_manage_financing(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    return get_tengasale_role(user) in {"merchant", "hq"}


def can_view_contract(user, contract):
    if can_manage_financing(user):
        return True
    return False
