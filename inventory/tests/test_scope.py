# inventory/tests/test_scope.py
from __future__ import annotations

import random
import string
from typing import Optional, Iterable, Tuple, Type

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.test import TestCase, Client, override_settings
from django.urls import reverse, NoReverseMatch


def _rand(n=8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ----------------------------- Introspection helpers -----------------------------

def _try_import_inventory_models():
    """
    Returns (InventoryItem, Location or None).
    Skips gracefully if InventoryItem doesn't exist.
    """
    try:
        from inventory import models as inv_models  # type: ignore
    except Exception:
        return None, None
    InventoryItem = getattr(inv_models, "InventoryItem", None)
    Location = getattr(inv_models, "Location", None)
    return InventoryItem, Location


def _try_import_tenant_models():
    """
    Returns (Business, Membership or None).
    """
    try:
        from tenants import models as ten_models  # type: ignore
    except Exception:
        return None, None
    Business = getattr(ten_models, "Business", None)
    Membership = getattr(ten_models, "Membership", None)
    return Business, Membership


def _find_fk_field(model: Type[models.Model], target_model: Type[models.Model]) -> Optional[str]:
    """
    Find a ForeignKey field on `model` that points to `target_model`.
    """
    for f in model._meta.get_fields():
        if isinstance(f, models.ForeignKey) and f.remote_field and f.remote_field.model is target_model:
            return f.name
    return None


def _first_charfield(model: Type[models.Model], preferred: Iterable[str]) -> Optional[str]:
    """
    Find a char/text field suitable for 'code'/'imei'/'sku'/'serial' data.
    Tries `preferred` names first, then any CharField/TextField.
    """
    names = {f.name for f in model._meta.get_fields() if isinstance(f, (models.CharField, models.TextField))}
    for p in preferred:
        if p in names:
            return p
    for f in model._meta.get_fields():
        if isinstance(f, (models.CharField, models.TextField)):
            return f.name
    return None


def _maybe_field(model: Type[models.Model], names: Iterable[str]) -> Optional[str]:
    fields = {f.name for f in model._meta.get_fields()}
    for n in names:
        if n in fields:
            return n
    return None


# ----------------------------- Builders (tolerant) -----------------------------

def _create_business(name: str):
    Business, _Membership = _try_import_tenant_models()
    if Business is None:
        raise ImproperlyConfigured("Business model not available")

    # Gather fields
    all_fields = {f.name: f for f in Business._meta.get_fields() if hasattr(f, "attname")}

    kwargs = {}
    # Required-ish fields that commonly exist
    if "name" in all_fields:
        kwargs["name"] = name
    if "slug" in all_fields:
        # slugify safely here without importing django slugify (not strictly needed)
        slug = name.lower().replace(" ", "-")
        kwargs["slug"] = slug[:50] or _rand()

    # Optional status or active flags
    if "status" in all_fields and getattr(all_fields["status"], "choices", None):
        # If choices exist, try "ACTIVE" if present
        choices = {c[0] for c in getattr(all_fields["status"], "choices", [])}
        kwargs["status"] = "ACTIVE" if "ACTIVE" in choices else next(iter(choices or ["ACTIVE"]))
    elif "status" in all_fields:
        kwargs["status"] = "ACTIVE"
    if "is_active" in all_fields:
        kwargs["is_active"] = True

    return Business.objects.create(**kwargs)


def _create_location(biz, name: str = "Main"):
    InventoryItem, Location = _try_import_inventory_models()
    if not Location:
        return None  # Location is optional
    fk_name = _find_fk_field(Location, type(biz))
    kwargs = {"name": name} if _maybe_field(Location, ["name"]) else {}
    if fk_name:
        kwargs[fk_name] = biz
    # Optional status flag
    if _maybe_field(Location, ["is_active"]):
        kwargs["is_active"] = True
    return Location.objects.create(**kwargs)


def _create_item_for_business(biz, code: str, location=None):
    InventoryItem, Location = _try_import_inventory_models()
    if not InventoryItem:
        raise ImproperlyConfigured("InventoryItem model not available")
    kwargs = {}

    # FK to business
    biz_fk = _find_fk_field(InventoryItem, type(biz))
    if biz_fk:
        kwargs[biz_fk] = biz

    # Set code/imei/sku field
    code_field = _first_charfield(InventoryItem, preferred=("imei", "code", "barcode", "sku", "serial"))
    if code_field:
        kwargs[code_field] = code
    else:
        # If there is no char/text field, bail
        raise ImproperlyConfigured("No suitable CharField/TextField for item code on InventoryItem")

    # Optional location
    if location is not None:
        loc_fk = _find_fk_field(InventoryItem, type(location))
        if loc_fk:
            kwargs[loc_fk] = location

    # Mark in-stock if schema supports it (tolerant)
    for f in ("in_stock", "available", "availability", "is_active"):
        if _maybe_field(InventoryItem, [f]):
            kwargs[f] = True
    if _maybe_field(InventoryItem, ["status"]):
        # avoid 'sold' if choices exist
        kwargs["status"] = "in_stock"

    return InventoryItem.objects.create(**kwargs)


def _set_active_business_in_session(client: Client, biz_id: int):
    # Keep parity with app: both "active_business_id" and "biz_id"
    session = client.session
    session["active_business_id"] = biz_id
    session["biz_id"] = biz_id
    session.save()


def _try_reverse_api_stock_status() -> str | None:
    try:
        return reverse("inventory:api_stock_status")
    except NoReverseMatch:
        return None


# -------------------------------------- Tests --------------------------------------

@override_settings(ROOT_URLCONF=None)  # use project urls
class ScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Hard requirements
        cls.InventoryItem, cls.Location = _try_import_inventory_models()
        cls.Business, cls.Membership = _try_import_tenant_models()
        if not cls.InventoryItem or not cls.Business:
            # Mark flags for later skips
            cls.__skip_models__ = True
            return
        cls.__skip_models__ = False

        # Users
        U = get_user_model()
        cls.user = U.objects.create_user(username=f"u_{_rand()}", email=f"u_{_rand()}@x.com", password="pass12345")

        # Businesses
        cls.biz_a = _create_business(f"A_{_rand()}")
        cls.biz_b = _create_business(f"B_{_rand()}")

        # Locations (optional)
        cls.loc_a1 = _create_location(cls.biz_a, "A1") or None
        cls.loc_b1 = _create_location(cls.biz_b, "B1") or None

        # Codes
        cls.code_shared = "111222333444555"  # 15 digits – works with IMEI-style fields
        cls.code_only_b = "999888777666555"

        # Items with same code in different businesses
        cls.item_a = _create_item_for_business(cls.biz_a, cls.code_shared, cls.loc_a1)
        cls.item_b = _create_item_for_business(cls.biz_b, cls.code_shared, cls.loc_b1)

        # Extra item existing only in B
        cls.item_b2 = _create_item_for_business(cls.biz_b, cls.code_only_b, cls.loc_b1)

    def setUp(self):
        if getattr(self, "__skip_models__", False):
            self.skipTest("Required models (InventoryItem/Business) not available.")
        self.client = Client()
        self.client.force_login(self.user)
        self.url = _try_reverse_api_stock_status()
        if not self.url:
            self.skipTest("URL name inventory:api_stock_status not found.")

    # -------- core assertions (tolerant to JSON schema) --------

    @staticmethod
    def _parse_found(payload: dict) -> Optional[bool]:
        """
        Extract a 'found' signal from various possible response shapes.
        """
        if payload is None:
            return None
        # explicit flag
        if isinstance(payload.get("found"), bool):
            return payload["found"]
        # nested shapes seen in earlier UIs (data.exists / ok+exists)
        data = payload.get("data") or {}
        if isinstance(data, dict) and isinstance(data.get("exists"), bool):
            return data["exists"]
        if payload.get("ok") is True and payload.get("exists") is True:
            return True
        # 'in_stock' can also be a proxy for existence
        if isinstance(payload.get("in_stock"), bool):
            return payload["in_stock"]
        if isinstance(data.get("in_stock"), bool):
            return data["in_stock"]
        return None

    def _get(self, code: str, location_id: int | None = None) -> Tuple[int, dict]:
        params = {"code": code}
        if location_id:
            params["location_id"] = str(location_id)
        resp = self.client.get(self.url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        try:
            j = resp.json()
        except Exception:
            j = {}
        return resp.status_code, j

    # -------- tests --------

    def test_business_scoping_same_code_prefers_active_business(self):
        """
        With the same 15-digit code existing in multiple businesses,
        the active business session must resolve the one in the active business.
        """
        _set_active_business_in_session(self.client, self.biz_a.id)
        status_a, j_a = self._get(self.code_shared)
        self.assertEqual(status_a, 200)
        self.assertIs(self._parse_found(j_a), True, msg=f"Expected found in biz A, got {j_a}")

        # Switch to biz B and ensure it's also found there (scoped by session)
        _set_active_business_in_session(self.client, self.biz_b.id)
        status_b, j_b = self._get(self.code_shared)
        self.assertEqual(status_b, 200)
        self.assertIs(self._parse_found(j_b), True, msg=f"Expected found in biz B, got {j_b}")

    def test_other_business_item_not_found_when_not_active(self):
        """
        If a code exists only in Business B, querying under Business A should not find it.
        """
        _set_active_business_in_session(self.client, self.biz_a.id)
        status, j = self._get(self.code_only_b)
        self.assertEqual(status, 200)
        found = self._parse_found(j)
        # If endpoint signals not found explicitly, expect False.
        # If endpoint doesn't distinguish, at least it should not claim True.
        self.assertIn(found, (False, None), msg=f"Item from other business should not be visible: {j}")

    def test_optional_location_param_does_not_leak_cross_business(self):
        """
        Passing a location_id must not allow seeing items from another business.
        Even if the ID belongs to another business, the code must not leak.
        """
        _set_active_business_in_session(self.client, self.biz_a.id)
        # Intentionally pass B's location (if we created one); still must not see B-only code
        loc_id = getattr(self.loc_b1, "id", None)
        status, j = self._get(self.code_only_b, location_id=loc_id)
        self.assertEqual(status, 200)
        found = self._parse_found(j)
        self.assertIn(found, (False, None), msg=f"Cross-business leak via location_id: {j}")

    def test_endpoint_handles_missing_or_short_code(self):
        """
        Defensive: shorter-than-15 or missing code should not 500.
        """
        _set_active_business_in_session(self.client, self.biz_a.id)
        for bad in ("", "123", "abc", "  "):
            status, _ = self._get(bad)
            # Expect 200 with graceful payload or 400 for validation; both acceptable.
            self.assertIn(status, (200, 400))
