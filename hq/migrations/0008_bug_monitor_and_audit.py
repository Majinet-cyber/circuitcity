# hq/migrations/0008_bug_monitor_and_audit.py
"""
Adds SystemIssue, SystemIssueOccurrence, AdminAuditLog models and
creates the HQ permission Groups on first deploy.
"""
import django.db.models.deletion
import django.utils.timezone
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hq", "0007_agentmilestone_hqpaymentmark_and_more"),
        ("tenants", "__first__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------
        # SystemIssue
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="SystemIssue",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("fingerprint", models.CharField(db_index=True, max_length=64, unique=True)),
                ("title", models.CharField(default="Unhandled exception", max_length=512)),
                ("error_type", models.CharField(blank=True, default="", max_length=255)),
                ("message", models.TextField(blank=True, default="")),
                ("status_code", models.SmallIntegerField(blank=True, null=True)),
                (
                    "severity",
                    models.CharField(
                        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")],
                        db_index=True,
                        default="high",
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("investigating", "Investigating"),
                            ("cleared", "Cleared"),
                            ("ignored", "Ignored"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                    ),
                ),
                ("path", models.CharField(blank=True, default="", max_length=2048)),
                ("method", models.CharField(blank=True, default="", max_length=16)),
                ("view_name", models.CharField(blank=True, default="", max_length=255)),
                ("app_label", models.CharField(blank=True, default="", max_length=100)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("device_family", models.CharField(blank=True, default="", max_length=128)),
                ("browser_family", models.CharField(blank=True, default="", max_length=128)),
                ("os_family", models.CharField(blank=True, default="", max_length=128)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("sanitized_get_params", models.JSONField(blank=True, default=dict)),
                ("sanitized_post_data", models.JSONField(blank=True, default=dict)),
                ("sanitized_payload", models.JSONField(blank=True, default=dict)),
                ("stack_trace", models.TextField(blank=True, default="")),
                ("environment", models.CharField(blank=True, default="", max_length=64)),
                ("release_version", models.CharField(blank=True, default="", max_length=128)),
                ("occurrence_count", models.PositiveIntegerField(default=1)),
                ("first_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("notes", models.TextField(blank=True, default="")),
                ("resolution_notes", models.TextField(blank=True, default="")),
                ("cleared_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_issues",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="system_issues",
                        to="tenants.business",
                    ),
                ),
                (
                    "cleared_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cleared_issues",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="system_issues",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "System Issue",
                "verbose_name_plural": "System Issues",
                "ordering": ["-last_seen_at"],
            },
        ),
        migrations.AddIndex(
            model_name="systemissue",
            index=models.Index(fields=["fingerprint"], name="hq_sysiss_fp_idx"),
        ),
        migrations.AddIndex(
            model_name="systemissue",
            index=models.Index(fields=["status", "severity"], name="hq_sysiss_stat_sev_idx"),
        ),
        migrations.AddIndex(
            model_name="systemissue",
            index=models.Index(fields=["status_code"], name="hq_sysiss_code_idx"),
        ),
        migrations.AddIndex(
            model_name="systemissue",
            index=models.Index(fields=["last_seen_at"], name="hq_sysiss_lastseen_idx"),
        ),
        migrations.AddIndex(
            model_name="systemissue",
            index=models.Index(fields=["assigned_to"], name="hq_sysiss_assignee_idx"),
        ),
        # ------------------------------------------------------------------
        # SystemIssueOccurrence
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="SystemIssueOccurrence",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("path", models.CharField(blank=True, default="", max_length=2048)),
                ("method", models.CharField(blank=True, default="", max_length=16)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("stack_trace", models.TextField(blank=True, default="")),
                ("sanitized_get_params", models.JSONField(blank=True, default=dict)),
                ("sanitized_post_data", models.JSONField(blank=True, default=dict)),
                ("sanitized_payload", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "issue",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="occurrences",
                        to="hq.systemissue",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="tenants.business",
                    ),
                ),
            ],
            options={
                "verbose_name": "Issue Occurrence",
                "verbose_name_plural": "Issue Occurrences",
                "ordering": ["-occurred_at"],
            },
        ),
        migrations.AddIndex(
            model_name="systemissueoccurrence",
            index=models.Index(fields=["issue", "occurred_at"], name="hq_sysoccur_issue_idx"),
        ),
        # ------------------------------------------------------------------
        # AdminAuditLog
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="AdminAuditLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(db_index=True, max_length=100)),
                ("target_model", models.CharField(blank=True, default="", max_length=100)),
                ("target_id", models.CharField(blank=True, default="", max_length=100)),
                ("target_repr", models.CharField(blank=True, default="", max_length=512)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="admin_audit_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Admin Audit Log",
                "verbose_name_plural": "Admin Audit Logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="adminauditlog",
            index=models.Index(fields=["actor", "created_at"], name="hq_adminlog_actor_idx"),
        ),
        migrations.AddIndex(
            model_name="adminauditlog",
            index=models.Index(fields=["action"], name="hq_adminlog_action_idx"),
        ),
        migrations.AddIndex(
            model_name="adminauditlog",
            index=models.Index(fields=["target_model", "target_id"], name="hq_adminlog_target_idx"),
        ),
        # ------------------------------------------------------------------
        # HQ Custom Permissions (via proxy model on ContentType)
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="HQPermissions",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
            ],
            options={
                "verbose_name": "HQ Permissions",
                "managed": False,
                "default_permissions": (),
                "permissions": [
                    ("can_view_hq_admin",       "Can view HQ admin"),
                    ("can_view_bug_monitor",    "Can view Bug Monitor"),
                    ("can_view_stack_traces",   "Can view stack traces"),
                    ("can_manage_bug_status",   "Can manage bug status"),
                    ("can_assign_bugs",         "Can assign bugs"),
                    ("can_view_audit_logs",     "Can view audit logs"),
                    ("can_manage_admin_roles",  "Can manage admin roles"),
                    ("can_view_business_data",  "Can view business data"),
                    ("can_manage_integrations", "Can manage integrations"),
                    ("can_view_webhooks",       "Can view webhooks"),
                ],
            },
        ),
    ]
