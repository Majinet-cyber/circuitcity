"""
Add public_token field to GymMember for short, non-guessable public status links.
Also backfills existing members with unique tokens.

Migration steps:
1. Add public_token field WITHOUT unique constraint (allow duplicates)
2. Backfill all existing members with unique tokens
3. Add unique constraint after backfill
"""
import secrets

from django.db import migrations, models


def generate_unique_public_token(apps, schema_editor):
    """Backfill existing GymMember records with unique public_token values."""
    GymMember = apps.get_model("inventory", "GymMember")
    
    # Track all generated tokens to ensure uniqueness
    existing_tokens = set(
        GymMember.objects.exclude(public_token="").exclude(public_token__isnull=True).values_list("public_token", flat=True)
    )
    
    members_to_update = GymMember.objects.filter(public_token="") | GymMember.objects.filter(public_token__isnull=True)
    
    for member in members_to_update:
        # Generate unique token
        for _ in range(100):  # More retries for safety
            token = secrets.token_urlsafe(16)[:22]
            if token not in existing_tokens:
                member.public_token = token
                existing_tokens.add(token)
                member.save(update_fields=["public_token"])
                break
        else:
            # Fallback: extremely unlikely but generate another token
            token = secrets.token_urlsafe(16)[:22]
            member.public_token = token
            member.save(update_fields=["public_token"])


def reverse_backfill(apps, schema_editor):
    """Clear public_token on reverse (for rollback safety, though typically no-op)."""
    # No-op: we don't want to lose tokens on rollback
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1018_clothingbarcodeunit"),
        ("inventory", "0115_alter_agentprofile_location"),
    ]

    operations = [
        # Step 1: Add the public_token field WITHOUT unique constraint
        # (unique=False initially to allow empty/null values during migration)
        migrations.AddField(
            model_name="gymmember",
            name="public_token",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Non-guessable token for public member status page (URL-safe)",
                max_length=22,
                null=True,  # Allow null temporarily
            ),
        ),
        # Step 2: Backfill existing members with unique tokens
        migrations.RunPython(generate_unique_public_token, reverse_backfill),
        # Step 3: Add unique constraint now that all values are populated
        migrations.AlterField(
            model_name="gymmember",
            name="public_token",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Non-guessable token for public member status page (URL-safe)",
                max_length=22,
                unique=True,
            ),
        ),
    ]
