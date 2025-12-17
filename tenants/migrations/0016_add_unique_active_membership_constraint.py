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

            # Rank: prefer location_id NOT NULL, then OWNER > MANAGER, then highest id
            qs = base_qs.annotate(
                loc_rank=Case(
                    When(location_id__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                role_rank=Case(
                    When(role="OWNER", then=Value(3)),
                    When(role="MANAGER", then=Value(2)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            ).order_by("-loc_rank", "-role_rank", "-id")

            keep = qs.first()
            if not keep:
                continue

            # Compute the best role across all duplicates
            best_role_qs = base_qs.annotate(
                role_rank=Case(
                    When(role="OWNER", then=Value(3)),
                    When(role="MANAGER", then=Value(2)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            ).order_by("-role_rank", "-id")
            
            best_role = best_role_qs.values_list("role", flat=True).first()
            
            # Promote the kept row's role if necessary
            if best_role and keep.role != best_role:
                Membership.objects.filter(id=keep.id).update(role=best_role)

            # Deactivate the rest (do NOT change their location_id)
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

