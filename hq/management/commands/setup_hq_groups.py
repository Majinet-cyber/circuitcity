# hq/management/commands/setup_hq_groups.py
"""
Management command: python manage.py setup_hq_groups

Creates the standard HQ permission groups with appropriate permissions.
Safe to run multiple times (idempotent).
"""
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand


# Group → list of permission codenames
HQ_GROUPS = {
    "HQ Super Admin": [
        "can_view_hq_admin",
        "can_view_bug_monitor",
        "can_view_stack_traces",
        "can_manage_bug_status",
        "can_assign_bugs",
        "can_view_audit_logs",
        "can_manage_admin_roles",
        "can_view_business_data",
        "can_manage_integrations",
        "can_view_webhooks",
    ],
    "HQ Operations Admin": [
        "can_view_hq_admin",
        "can_view_bug_monitor",
        "can_manage_bug_status",
        "can_assign_bugs",
        "can_view_audit_logs",
        "can_view_business_data",
    ],
    "Bug Monitor Admin": [
        "can_view_hq_admin",
        "can_view_bug_monitor",
        "can_view_stack_traces",
        "can_manage_bug_status",
        "can_assign_bugs",
    ],
    "Support Agent": [
        "can_view_hq_admin",
        "can_view_bug_monitor",
        "can_view_business_data",
    ],
    "Developer / Engineer": [
        "can_view_hq_admin",
        "can_view_bug_monitor",
        "can_view_stack_traces",
        "can_manage_bug_status",
        "can_assign_bugs",
        "can_view_audit_logs",
    ],
    "Read Only Auditor": [
        "can_view_hq_admin",
        "can_view_audit_logs",
    ],
    "Business Manager": [
        "can_view_hq_admin",
        "can_view_business_data",
    ],
    # Legacy group — keep existing behaviour
    "platform_admin": [
        "can_view_hq_admin",
        "can_view_bug_monitor",
        "can_manage_bug_status",
        "can_assign_bugs",
        "can_view_audit_logs",
        "can_view_business_data",
    ],
}


class Command(BaseCommand):
    help = "Create or update HQ permission groups (idempotent)."

    def handle(self, *args, **options):
        from hq.models_bugmonitor import SystemIssue

        ct = ContentType.objects.get_for_model(SystemIssue)
        created_groups = []
        updated_groups = []

        for group_name, codenames in HQ_GROUPS.items():
            group, created = Group.objects.get_or_create(name=group_name)
            perms = Permission.objects.filter(content_type=ct, codename__in=codenames)
            group.permissions.set(perms)

            if created:
                created_groups.append(group_name)
            else:
                updated_groups.append(group_name)

        if created_groups:
            self.stdout.write(self.style.SUCCESS(f"Created: {', '.join(created_groups)}"))
        if updated_groups:
            self.stdout.write(f"Updated: {', '.join(updated_groups)}")

        self.stdout.write(self.style.SUCCESS("HQ groups setup complete."))
