# Manual migration to add unique constraint for active memberships
# Created: 2025-12-17

from django.db import migrations, models, transaction
from django.db.models import Count, Case, When, Value, IntegerField, Q


def dedupe_active_memberships(apps, schema_editor):
    Membership = apps.get_model("tenants", "Membership")

    dupes = (
        Membership.objects.filter(status="ACTIVE")
        .values("user_id", "business_id")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )

    for d in dupes:
        with transaction.atomic():
            base_qs = Membership.objects.filter(
                status="ACTIVE",
                user_id=d["user_id"],
                business_id=d["business_id"],
            )

            # Rank: prefer MANAGER, then rows with location, then newest id
            qs = base_qs.annotate(
                role_rank=Case(
                    When(role="MANAGER", then=Value(2)),
                    When(role="OWNER", then=Value(3)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                loc_rank=Case(
                    When(location_id__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            ).order_by("-role_rank", "-loc_rank", "-id")

            keep = qs.first()
            if not keep:
                continue

            # If keep has no location, copy from another duplicate that has it
            if getattr(keep, "location_id", None) is None:
                donor = base_qs.filter(location_id__isnull=False).exclude(id=keep.id).order_by("-id").first()
                if donor:
                    keep.location_id = donor.location_id
                    keep.save(update_fields=["location_id"])

            # Deactivate the rest
            base_qs.exclude(id=keep.id).update(status="INACTIVE")


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0015_alter_business_business_kind"),
    ]

    operations = [
        migrations.RunPython(dedupe_active_memberships, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(
                fields=["user", "business"],
                condition=Q(status="ACTIVE"),
                name="uniq_active_membership_user_business",
            ),
        ),
    ]

