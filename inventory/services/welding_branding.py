from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WeldingBrandingProfile:
    company_name: str
    phone: str
    email: str
    address: str
    city: str
    payment_instructions: str
    terms: str
    signature_name: str
    logo: object | None = None
    signature_image: object | None = None


DEFAULT_TERMS = (
    "This quotation is valid for 30 days from the date of issue.\n"
    "Work starts after deposit confirmation.\n"
    "Final payment is due on completion before delivery.\n"
    "Changes outside the quoted scope may be billed separately."
)


def get_or_create_branding_settings(business):
    from inventory.models_welding import WeldingBrandingSettings

    settings, _created = WeldingBrandingSettings.objects.get_or_create(
        business=business,
        defaults={"company_name": getattr(business, "name", "") or ""},
    )
    return settings


def branding_profile_for_business(business) -> WeldingBrandingProfile:
    settings = get_or_create_branding_settings(business)
    return WeldingBrandingProfile(
        company_name=(settings.company_name or getattr(business, "name", "") or "Welding Workshop").strip(),
        phone=(settings.business_phone or getattr(business, "phone", "") or "").strip(),
        email=(settings.business_email or getattr(business, "email", "") or "").strip(),
        address=(settings.business_address or getattr(business, "address", "") or "").strip(),
        city=(settings.city or "").strip(),
        payment_instructions=(settings.payment_instructions or "").strip(),
        terms=(settings.default_terms or DEFAULT_TERMS).strip(),
        signature_name=(settings.authorized_signature_name or "").strip(),
        logo=settings.company_logo if settings.company_logo else None,
        signature_image=settings.signature_image if settings.signature_image else None,
    )


def branding_snapshot_for_business(business) -> dict[str, str]:
    profile = branding_profile_for_business(business)
    return {
        "company_name": profile.company_name,
        "phone": profile.phone,
        "email": profile.email,
        "address": profile.address,
        "city": profile.city,
        "payment_instructions": profile.payment_instructions,
        "terms": profile.terms,
        "signature_name": profile.signature_name,
    }


def branding_profile_for_quote(quote, business=None) -> WeldingBrandingProfile:
    business = business or getattr(quote, "business", None)
    live_profile = branding_profile_for_business(business)
    snapshot = getattr(quote, "branding_snapshot", None) or {}
    return WeldingBrandingProfile(
        company_name=snapshot.get("company_name") or live_profile.company_name,
        phone=snapshot.get("phone") or live_profile.phone,
        email=snapshot.get("email") or live_profile.email,
        address=snapshot.get("address") or live_profile.address,
        city=snapshot.get("city") or live_profile.city,
        payment_instructions=snapshot.get("payment_instructions") or live_profile.payment_instructions,
        terms=snapshot.get("terms") or live_profile.terms,
        signature_name=snapshot.get("signature_name") or live_profile.signature_name,
        logo=live_profile.logo,
        signature_image=live_profile.signature_image,
    )
