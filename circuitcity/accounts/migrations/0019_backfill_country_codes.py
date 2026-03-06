# Generated migration: backfill Profile.country from free-text to ISO-2 codes
from django.db import migrations

# Map common legacy free-text country names to ISO-2 codes
COUNTRY_NAME_TO_ISO2 = {
    "malawi": "MW",
    "zambia": "ZM",
    "kenya": "KE",
    "tanzania": "TZ",
    "south africa": "ZA",
    "nigeria": "NG",
    "ghana": "GH",
    "uganda": "UG",
    "zimbabwe": "ZW",
    "mozambique": "MZ",
    "ethiopia": "ET",
    "rwanda": "RW",
    "botswana": "BW",
    "namibia": "NA",
    "egypt": "EG",
    "morocco": "MA",
    "senegal": "SN",
    "cameroon": "CM",
    "angola": "AO",
    "sudan": "SD",
    "madagascar": "MG",
    "mali": "ML",
    "burkina faso": "BF",
    "malawi (default)": "MW",
}


def forwards(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    for profile in Profile.objects.all():
        country = (profile.country or "").strip()
        if not country:
            profile.country = "MW"
            profile.save(update_fields=["country"])
            continue
        # If it already looks like an ISO-2 code (2 uppercase letters), leave it
        if len(country) <= 3 and country.upper() == country and country.isalpha():
            continue
        # Normalize free-text to ISO-2
        normalized = COUNTRY_NAME_TO_ISO2.get(country.lower())
        if normalized:
            profile.country = normalized
        else:
            # Unknown free-text → default to Malawi
            profile.country = "MW"
        profile.save(update_fields=["country"])


def backwards(apps, schema_editor):
    # Non-reversible; leave as-is
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_profile_country_currency_upgrade"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
