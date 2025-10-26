# core/context.py
from __future__ import annotations

from types import SimpleNamespace
from typing import Dict, Iterable, Optional

from django.conf import settings
from django.contrib.auth.models import Group
from django.http import HttpRequest


def _extract_roles_for(user, business) -> SimpleNamespace:
    """
    Determine tenant-scoped roles for the current user on the current business.

    Roles come from Django Groups named with the pattern:  biz:{BUSINESS_ID}:{ROLE}
      e.g., biz:3:OWNER , biz:3:MANAGER , biz:3:AGENT , biz:3:AUDITOR

    Returns SimpleNamespace(
        is_owner: bool,
        is_manager: bool,
        is_agent: bool,
        is_auditor: bool,
        roles: list[str],
    )
    """
    is_owner = is_manager = is_agent = is_auditor = False
    roles: Iterable[str] = []

    if not (user and getattr(user, "is_authenticated", False) and business):
        return SimpleNamespace(
            is_owner=False,
            is_manager=False,
            is_agent=False,
            is_auditor=False,
            roles=[],
        )

    prefix = f"biz:{business.pk}:"
    names = (
        user.groups.filter(name__startswith=prefix)
        .values_list("name", flat=True)
    )

    found = []
    for name in names:
        # name looks like "biz:123:MANAGER"
        try:
            role = name.split(":", 2)[2]
        except Exception:
            continue
        found.append(role.upper())

    roles = sorted(set(found))
    is_owner = "OWNER" in roles
    is_manager = is_owner or ("MANAGER" in roles)  # OWNER implies manager privileges
    is_agent = "AGENT" in roles
    is_auditor = "AUDITOR" in roles

    return SimpleNamespace(
        is_owner=is_owner,
        is_manager=is_manager,
        is_agent=is_agent,
        is_auditor=is_auditor,
        roles=roles,
    )


def _features_for(request: HttpRequest, business) -> SimpleNamespace:
    """
    Build a safe FEATURES object for templates.
    Priority (low -> high):
      1) sane defaults
      2) settings.FEATURES (dict, optional)
      3) per-business attributes if present (e.g., business.feature_layby)

    Result is accessible like: FEATURES.LAYBY, FEATURES.SIMULATOR, etc.
    """
    # 1) Defaults
    cfg: Dict[str, bool] = {
        "LAYBY": True,
        "SIMULATOR": True,
    }

    # 2) settings.FEATURES can override defaults (optional)
    settings_features = getattr(settings, "FEATURES", None)
    if isinstance(settings_features, dict):
        for k, v in settings_features.items():
            # only simple bool flags here
            try:
                cfg[str(k).upper()] = bool(v)
            except Exception:
                pass

    # 3) Per-business overrides if such attributes exist
    if business is not None:
        for key in list(cfg.keys()):
            attr = f"feature_{key.lower()}"  # e.g., feature_layby
            if hasattr(business, attr):
                try:
                    cfg[key] = bool(getattr(business, attr))
                except Exception:
                    pass

    return SimpleNamespace(**cfg)


def flags(request: HttpRequest) -> dict:
    """
    Context processor: adds role flags, features, and app name to all templates.

    Add to settings.py:
        TEMPLATES[0]['OPTIONS']['context_processors'] += [
            'django.template.context_processors.request',
            'core.context.flags',
        ]
    """
    user = getattr(request, "user", None)
    business = getattr(request, "business", None)  # set by your require_business/middleware

    roles = _extract_roles_for(user, business)
    features = _features_for(request, business)

    app_name = getattr(settings, "APP_NAME", "Circuit City")

    return {
        # App/brand
        "APP_NAME": app_name,

        # Tenant context (useful if templates want to show/hide by tenant presence)
        "BUSINESS": business,

        # Roles (what your sidebar checks)
        "IS_OWNER": roles.is_owner,
        "IS_MANAGER": roles.is_manager,
        "IS_AGENT": roles.is_agent,
        "IS_AUDITOR": roles.is_auditor,
        "ROLES": roles.roles,  # ['OWNER', 'MANAGER', ...] for debugging/visibility

        # Feature flags (safe even if missing in settings or business)
        "FEATURES": features,

        # Convenience booleans you might like
        "DEBUG": getattr(settings, "DEBUG", False),
    }


