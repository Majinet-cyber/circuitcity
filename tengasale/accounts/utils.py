from django.urls import reverse


def is_hq(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="HQ").exists()
    )


def is_underwriter(user):
    return user.is_authenticated and (
        user.groups.filter(name="Underwriter").exists()
        or user.groups.filter(name="Manager").exists()
        or (user.is_staff and not user.is_superuser)
    )


def is_merchant(user):
    return user.is_authenticated and user.groups.filter(name="Merchant").exists()


def primary_role(user):
    if is_hq(user):
        return "hq"
    if is_underwriter(user):
        return "underwriter"
    if is_merchant(user):
        return "merchant"
    return "merchant"


def role_redirect_url(user):
    role = primary_role(user)
    if role == "hq":
        return reverse("hq_dashboard")
    if role == "underwriter":
        return reverse("underwriter_dashboard")
    return reverse("merchant_dashboard")
