from django.urls import reverse

from .models import UserProfile


ROLE_GROUPS = {
    "merchant": "Merchant",
    "underwriter": "Underwriter",
    "hq": "HQ",
}


def profile_role(user):
    if not user.is_authenticated:
        return None
    try:
        role = user.profile.role
    except UserProfile.DoesNotExist:
        return None
    if role == "manager":
        return "underwriter"
    return role or None


def has_role_group(user, role):
    group_name = ROLE_GROUPS[role]
    return user.groups.filter(name=group_name).exists()


def is_hq(user):
    return user.is_authenticated and profile_role(user) == "hq"


def is_underwriter(user):
    return user.is_authenticated and profile_role(user) == "underwriter"


def is_merchant(user):
    return user.is_authenticated and profile_role(user) == "merchant"


def primary_role(user):
    if is_hq(user):
        return "hq"
    if is_underwriter(user):
        return "underwriter"
    if is_merchant(user):
        return "merchant"
    return None


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
