# Generated manually to avoid conflicts with existing models

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hq", "0003_add_merchant_contract"),
        ("tenants", "0013_add_location_tracking"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Create new support models
        migrations.CreateModel(
            name="BusinessNote",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "title",
                    models.CharField(help_text="Short title for quick reference", max_length=255),
                ),
                ("content", models.TextField(help_text="Detailed note content")),
                (
                    "is_pinned",
                    models.BooleanField(
                        default=True,
                        help_text="If True, shown prominently on business detail page",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "author",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="business_notes_authored",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pinned_notes",
                        to="tenants.business",
                    ),
                ),
            ],
            options={
                "verbose_name": "Business Note",
                "verbose_name_plural": "Business Notes",
                "ordering": ["-is_pinned", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SupportActionLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("EXTEND_SUBSCRIPTION", "Extended Subscription"),
                            ("REVOKE_SUBSCRIPTION", "Revoked Subscription"),
                            ("SUSPEND_SUBSCRIPTION", "Suspended Subscription"),
                            ("ACTIVATE_SUBSCRIPTION", "Activated Subscription"),
                            ("CHANGE_PLAN", "Changed Plan"),
                            ("ADD_GRACE_DAYS", "Added Grace Days"),
                            ("FORCE_LOGOUT", "Force Logout"),
                            ("RESET_PASSWORD", "Reset Password"),
                            ("UNLOCK_ACCOUNT", "Unlocked Account"),
                            ("RESEND_OTP", "Resent OTP"),
                            ("VERIFY_EMAIL", "Verified Email"),
                            ("IMPERSONATE_USER", "Impersonated User"),
                            ("END_IMPERSONATION", "Ended Impersonation"),
                            ("RESTORE_STOCK", "Restored Stock"),
                            ("ARCHIVE_STOCK", "Archived Stock"),
                            ("REVERSE_TRANSACTION", "Reversed Transaction"),
                            ("FIX_DUPLICATE", "Fixed Duplicate Entry"),
                            ("HARD_DELETE", "Hard Delete"),
                            ("RECORD_MANUAL_PAYMENT", "Recorded Manual Payment"),
                            ("APPLY_CREDIT", "Applied Credit"),
                            ("APPLY_DISCOUNT", "Applied Discount"),
                            ("REFUND_PAYMENT", "Refunded Payment"),
                            ("RESEND_RECEIPT", "Resent Receipt"),
                            ("VIEW_BUSINESS", "Viewed Business"),
                            ("VIEW_DASHBOARD", "Viewed Dashboard"),
                            ("EXPORT_DATA", "Exported Data"),
                            ("CREATE_TICKET", "Created Support Ticket"),
                            ("UPDATE_TICKET", "Updated Support Ticket"),
                            ("ADD_NOTE", "Added Note"),
                            ("OTHER", "Other Action"),
                        ],
                        db_index=True,
                        help_text="Type of action performed",
                        max_length=32,
                    ),
                ),
                (
                    "reason",
                    models.TextField(help_text="Required explanation/justification for this action"),
                ),
                (
                    "payload_before",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="State before the action (for reversibility)",
                    ),
                ),
                (
                    "payload_after",
                    models.JSONField(blank=True, default=dict, help_text="State after the action"),
                ),
                (
                    "entity_type",
                    models.CharField(
                        blank=True,
                        help_text="Type of entity affected (Subscription, User, Stock, etc.)",
                        max_length=64,
                    ),
                ),
                (
                    "entity_id",
                    models.CharField(blank=True, help_text="ID of the affected entity", max_length=64),
                ),
                (
                    "ip_address",
                    models.GenericIPAddressField(blank=True, help_text="IP address of the actor", null=True),
                ),
                (
                    "user_agent",
                    models.TextField(blank=True, help_text="User agent of the actor"),
                ),
                (
                    "created_at",
                    models.DateTimeField(db_index=True, default=django.utils.timezone.now, editable=False),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        help_text="HQ staff member who performed this action",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="support_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        help_text="Business this action affected",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="support_actions",
                        to="tenants.business",
                    ),
                ),
            ],
            options={
                "verbose_name": "Support Action Log",
                "verbose_name_plural": "Support Action Logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SupportTicket",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "ticket_number",
                    models.CharField(
                        db_index=True,
                        help_text="Human-readable ticket number (e.g., HQ-2025-001234)",
                        max_length=20,
                        unique=True,
                    ),
                ),
                (
                    "requester_email",
                    models.EmailField(
                        blank=True,
                        help_text="Contact email if requester not in system",
                        max_length=254,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("login", "Login/Access Issue"),
                            ("payment", "Payment/Billing Issue"),
                            ("data", "Data/Inventory Issue"),
                            ("bug", "Bug Report"),
                            ("feature", "Feature Request"),
                            ("performance", "Performance Issue"),
                            ("other", "Other"),
                        ],
                        db_index=True,
                        default="other",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                            ("urgent", "Urgent"),
                        ],
                        db_index=True,
                        default="medium",
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("in_progress", "In Progress"),
                            ("waiting_customer", "Waiting on Customer"),
                            ("resolved", "Resolved"),
                            ("closed", "Closed"),
                        ],
                        db_index=True,
                        default="open",
                        max_length=20,
                    ),
                ),
                (
                    "title",
                    models.CharField(help_text="Short description of the issue", max_length=255),
                ),
                (
                    "description",
                    models.TextField(help_text="Detailed description of the issue"),
                ),
                (
                    "meta",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Additional metadata (e.g., error logs, screenshots)",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assigned_to",
                    models.ForeignKey(
                        blank=True,
                        help_text="HQ staff member assigned to this ticket",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="support_tickets_assigned",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="support_tickets",
                        to="tenants.business",
                    ),
                ),
                (
                    "requester",
                    models.ForeignKey(
                        blank=True,
                        help_text="User who requested support (if applicable)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="support_tickets_requested",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Support Ticket",
                "verbose_name_plural": "Support Tickets",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SupportNote",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "note_type",
                    models.CharField(
                        choices=[
                            ("comment", "Comment"),
                            ("status_change", "Status Change"),
                            ("action", "Action Taken"),
                            ("system", "System Note"),
                        ],
                        default="comment",
                        max_length=20,
                    ),
                ),
                ("content", models.TextField(help_text="Note content")),
                (
                    "is_internal",
                    models.BooleanField(default=False, help_text="If True, only visible to HQ staff"),
                ),
                ("meta", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "author",
                    models.ForeignKey(
                        help_text="User who added this note",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="support_notes_authored",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notes",
                        to="hq.supportticket",
                    ),
                ),
            ],
            options={
                "verbose_name": "Support Note",
                "verbose_name_plural": "Support Notes",
                "ordering": ["created_at"],
            },
        ),
        # Add indexes
        migrations.AddIndex(
            model_name="businessnote",
            index=models.Index(
                fields=["business", "is_pinned", "-created_at"],
                name="hq_business_busines_eb0d81_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportactionlog",
            index=models.Index(
                fields=["business", "-created_at"],
                name="hq_supporta_busines_dc10bb_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportactionlog",
            index=models.Index(fields=["actor", "-created_at"], name="hq_supporta_actor_i_b8e39c_idx"),
        ),
        migrations.AddIndex(
            model_name="supportactionlog",
            index=models.Index(
                fields=["action_type", "-created_at"],
                name="hq_supporta_action__644feb_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportactionlog",
            index=models.Index(
                fields=["business", "action_type", "-created_at"],
                name="hq_supporta_busines_7eb091_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(
                fields=["business", "status", "-created_at"],
                name="hq_supportt_busines_a1eebf_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(
                fields=["assigned_to", "status", "-created_at"],
                name="hq_supportt_assigne_eb97cc_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(
                fields=["category", "status", "-created_at"],
                name="hq_supportt_categor_cd0197_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(
                fields=["priority", "status", "-created_at"],
                name="hq_supportt_priorit_aae70d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportnote",
            index=models.Index(fields=["ticket", "created_at"], name="hq_supportn_ticket__5c6000_idx"),
        ),
    ]
