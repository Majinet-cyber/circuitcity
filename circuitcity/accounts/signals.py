# accounts/signals.py
from __future__ import annotations

from django.db import connection
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Profile, LoginSecurity, PasswordResetCode

User = get_user_model()


def _table_exists(model_cls) -> bool:
    """
    Return True if the DB table for model_cls exists.
    Prevents OperationalError during initial migrations.
    """
    try:
        names = set(connection.introspection.table_names())
        return model_cls._meta.db_table in names
    except Exception:
        return False


@receiver(post_save, sender=User)
def ensure_user_related_rows(sender, instance: User, created: bool, **kwargs):
    """
    Ensure each user has Profile and LoginSecurity rows.
    Safe when tables are not created yet (returns early).
    """
    # If tables aren't ready, skip silently (e.g., first migrate)
    if not _table_exists(Profile) or not _table_exists(LoginSecurity):
        return

    if created:
        Profile.objects.get_or_create(user=instance)
        LoginSecurity.objects.get_or_create(user=instance)
        return

    # Profile
    try:
        getattr(instance, "profile")
    except Profile.DoesNotExist:
        Profile.objects.get_or_create(user=instance)
    except AttributeError:
        pass

    # LoginSecurity
    try:
        getattr(instance, "login_sec")
    except LoginSecurity.DoesNotExist:
        LoginSecurity.objects.get_or_create(user=instance)
    except AttributeError:
        pass


@receiver(pre_save, sender=User)
def reset_login_security_on_password_change(sender, instance: User, **kwargs):
    """
    When password changes, reset staged lockouts.
    Skip if table doesn't exist yet.
    """
    if not instance.pk or not _table_exists(LoginSecurity):
        return

    try:
        old = sender.objects.only("password").get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    if old.password != instance.password:
        sec, _ = LoginSecurity.objects.get_or_create(user=instance)
        sec.stage = 0
        sec.fail_count = 0
        sec.locked_until = None
        sec.hard_blocked = False
        sec.save(update_fields=["stage", "fail_count", "locked_until", "hard_blocked"])


@receiver(post_save, sender=PasswordResetCode)
def prune_expired_reset_codes(sender, instance: PasswordResetCode, created: bool, **kwargs):
    """
    After creating a new code, prune expired unused ones.
    Skip if table isn't available (early bootstrap).
    """
    if not created or not _table_exists(PasswordResetCode):
        return
    PasswordResetCode.objects.filter(
        user=instance.user,
        used=False,
        expires_at__lt=timezone.now(),
    ).delete()


