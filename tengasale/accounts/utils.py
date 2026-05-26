from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from .models import UserProfile


ROLE_GROUPS = {
    "merchant": "Merchant",
    "underwriter": "Underwriter",
    "hq": "HQ",
}


VALID_PORTAL_ROLES = set(ROLE_GROUPS)


def profile_role(user):
    if not user.is_authenticated:
        return None
    try:
        role = user.profile.role
    except ObjectDoesNotExist:
        return None
    if role == "manager":
        return "underwriter"
    return role or None


def get_tengasale_role(user):
    if not user or not user.is_authenticated:
        return None

    role = profile_role(user)
    if role in VALID_PORTAL_ROLES:
        return role

    if user.is_superuser or user.is_staff:
        return "hq"

    return None


def get_user_portal_role(user):
    return get_tengasale_role(user)


def has_role_group(user, role):
    group_name = ROLE_GROUPS[role]
    return user.groups.filter(name=group_name).exists()


def is_hq(user):
    return get_user_portal_role(user) == "hq"


def is_underwriter(user):
    return get_user_portal_role(user) == "underwriter"


def is_merchant(user):
    return get_user_portal_role(user) == "merchant"


def primary_role(user):
    return get_user_portal_role(user)


def role_redirect_url(user):
    role = primary_role(user)
    if role == "hq":
        return reverse("hq_dashboard")
    if role == "underwriter":
        return reverse("underwriter_dashboard")
    if role == "merchant":
        return reverse("merchant_dashboard")
    return reverse("no_role")


def assign_role(user, role):
    if role not in ROLE_GROUPS:
        raise ValueError(f"Unknown role: {role}")

    for group_name in ROLE_GROUPS.values():
        user.groups.remove(*user.groups.filter(name=group_name))

    from django.contrib.auth.models import Group

    group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[role])
    user.groups.add(group)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = role
    profile.save(update_fields=["role"])
    user._state.fields_cache["profile"] = profile
