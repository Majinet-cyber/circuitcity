from django.db import migrations


def assign_hq_to_staff_and_superusers(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("accounts", "UserProfile")

    users = User.objects.filter(is_active=True).filter(is_staff=True) | User.objects.filter(
        is_active=True,
        is_superuser=True,
    )
    for user in users.distinct():
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.role:
            profile.role = "hq"
            profile.save(update_fields=["role"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_userprofile_role_alter_userprofile_user"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(assign_hq_to_staff_and_superusers, migrations.RunPython.noop),
    ]
