# sales/management/commands/backfill_sales_for_sold.py
from __future__ import annotations

from typing import Optional
from decimal import Decimal

from django.core.management import BaseCommand, CommandError
from django.db import transaction, models
from django.utils import timezone

# ----------------- tolerant imports -----------------
def _try_import(modpath: str, attr: str | None = None):
    import importlib
    try:
        mod = importlib.import_module(modpath)
        return getattr(mod, attr) if attr else mod
    except Exception:
        return None


Sale = _try_import("sales.models", "Sale")
InvItem = (
    _try_import("inventory.models", "InventoryItem")
    or _try_import("inventory.models", "Stock")
)
Location = (
    _try_import("inventory.models", "Location")
    or _try_import("tenants.models", "Location")
)
User = _try_import("django.contrib.auth.models", "User")

# Optional “finalize” helpers (any that exist will be tried if --finalize is set)
_finalize_sale = (
    _try_import("sales.services", "finalize_sale")
    or _try_import("sales.utils", "finalize_sale")
    or _try_import("inventory.services", "finalize_sale")
)


# ----------------- tiny helpers -----------------
def _model_has_field(model, name: str) -> bool:
    if model is None:
        return False
    try:
        return any(getattr(f, "name", None) == name for f in model._meta.get_fields())  # type: ignore[attr-defined]
    except Exception:
        return False


def _manager(model):
    if hasattr(model, "_base_manager"):
        return model._base_manager
    if hasattr(model, "all_objects"):
        return model.all_objects
    return model.objects


def _joinables(model) -> list[str]:
    want = [
        "business",
        "product",
        "current_location",
        "location",
        "assigned_agent",
        "sold_by",
        "sale",
        "agent",
    ]
    have = []
    try:
        fieldnames = {getattr(f, "name", None) for f in model._meta.get_fields()}  # type: ignore[attr-defined]
        for w in want:
            if w in fieldnames:
                have.append(w)
    except Exception:
        pass
    return have


def _first(*vals):
    for v in vals:
        if v not in (None, ""):
            return v
    return None


def _get_qty(it) -> int:
    return int(getattr(it, "quantity", getattr(it, "qty", 0)) or 0)


def _is_soldish(it) -> bool:
    status_val = str(getattr(it, "status", "") or "").strip().lower()
    return any(
        [
            bool(getattr(it, "sold_at", None)),
            bool(getattr(it, "is_sold", False)),
            status_val in {"sold", "completed", "closed"},
            (hasattr(it, "in_stock") and getattr(it, "in_stock") is False),
            (hasattr(it, "available") and getattr(it, "available") is False),
            (hasattr(it, "availability") and not getattr(it, "availability")),
            (hasattr(it, "quantity") and _get_qty(it) <= 0),
            (hasattr(it, "qty") and _get_qty(it) <= 0),
        ]
    )


def _resolve_location(it, location_id_default: Optional[int]) -> Optional[object]:
    # 1) from item
    loc = getattr(it, "current_location", None) or getattr(it, "location", None)
    if loc:
        return loc
    # 2) explicit default id
    if location_id_default and Location is not None:
        try:
            loc = Location.objects.filter(pk=int(location_id_default)).first()
            if loc:
                return loc
        except Exception:
            pass
    # 3) first location for same business (best effort)
    if Location is not None:
        try:
            qs = Location.objects.all()
            biz = getattr(it, "business", None)
            if biz is not None:
                for fk in ("business_id", "tenant_id", "company_id", "org_id"):
                    if hasattr(Location, fk):
                        try:
                            qs = qs.filter(**{fk: getattr(biz, "id", None)})
                            break
                        except Exception:
                            pass
            loc = qs.order_by("id").first()
            if loc:
                return loc
        except Exception:
            pass
    return None


def _resolve_agent(it, agent_id_default: Optional[int]):
    """
    Resolve a Salesperson object for Sale.agent:
      1) item.assigned_agent / item.sold_by
      2) --agent-id-default (FK model behind Sale.agent)
      3) last resort: first auth.User if FK targets auth.User
    """
    agent = getattr(it, "assigned_agent", None) or getattr(it, "sold_by", None)
    if agent:
        return agent

    if agent_id_default and Sale is not None:
        try:
            if _model_has_field(Sale, "agent"):
                f = Sale._meta.get_field("agent")  # type: ignore[attr-defined]
                rel_model = getattr(f, "remote_field", None) and getattr(f.remote_field, "model", None)
                if rel_model is not None:
                    obj = rel_model._default_manager.filter(pk=int(agent_id_default)).first()
                    if obj:
                        return obj
        except Exception:
            pass

    try:
        if _model_has_field(Sale, "agent"):
            f = Sale._meta.get_field("agent")  # type: ignore[attr-defined]
            rel_model = getattr(f, "remote_field", None) and getattr(f.remote_field, "model", None)
            if rel_model is User and User is not None:
                u = User.objects.order_by("id").first()
                if u:
                    return u
    except Exception:
        pass

    return None


def _sale_exists_for_item(it) -> bool:
    if Sale is None:
        return False
    # Prefer strong FK check
    for fk in ("inventory_item", "item"):
        if _model_has_field(Sale, fk):
            try:
                if Sale.objects.filter(**{fk: it}).exists():
                    return True
            except Exception:
                pass
    # Fallback: match by IMEI/Barcode
    imei = getattr(it, "imei", None)
    barcode = getattr(it, "barcode", None)
    q = models.Q()
    if imei and _model_has_field(Sale, "imei"):
        q |= models.Q(imei=imei)
    if barcode and _model_has_field(Sale, "barcode"):
        q |= models.Q(barcode=barcode)
    if q:
        try:
            return Sale.objects.filter(q).exists()
        except Exception:
            pass
    return False


def _price_from_item(it) -> Decimal:
    p = _first(getattr(it, "sold_price", None), getattr(it, "price", None))
    try:
        return Decimal(p).quantize(Decimal("1.00")) if p is not None else Decimal("0.00")
    except Exception:
        return Decimal("0.00")


def _sold_at_from_item(it):
    return getattr(it, "sold_at", None) or timezone.now()


def _set_item_sold_flags(it):
    """Best-effort: normalize item as SOLD (idempotent)."""
    changed = False
    now = timezone.now()

    if hasattr(it, "status"):
        if str(getattr(it, "status") or "").lower() != "sold":
            it.status = "sold"
            changed = True

    for fld, val in (("is_sold", True), ("in_stock", False), ("available", False), ("availability", False)):
        if hasattr(it, fld):
            if getattr(it, fld, None) not in (val,):
                setattr(it, fld, val)
                changed = True

    if hasattr(it, "sold_at") and not getattr(it, "sold_at", None):
        it.sold_at = now
        changed = True

    # If it tracks quantity/qty, clamp to 0 (not negative)
    for qf in ("quantity", "qty"):
        if hasattr(it, qf):
            if int(getattr(it, qf) or 0) != 0:
                setattr(it, qf, 0)
                changed = True

    return changed


# ----------------- command -----------------
class Command(BaseCommand):
    help = (
        "Create sales.Sale rows for items already marked SOLD (or equivalent). "
        "Skips items that already have a Sale. Can optionally finalize or fix item flags."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5000, help="Max items to scan")
        parser.add_argument("--business-id", type=int, default=None, help="Only backfill for this business id")
        parser.add_argument("--location-id-default", type=int, default=None, help="Default Location id when item has none")
        parser.add_argument("--agent-id-default", type=int, default=None, help="Default Agent/User id when item provides none")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be created without saving")
        parser.add_argument("--verbose", action="store_true", help="Print per-item actions")
        parser.add_argument("--finalize", action="store_true", help="Call a finalize_sale helper if available")
        parser.add_argument("--fix-item", action="store_true", help="Normalize item flags to SOLD after creating a Sale")

    def handle(self, *args, **opts):
        if Sale is None:
            raise CommandError("sales.models.Sale not importable.")
        if InvItem is None:
            raise CommandError("inventory.models.InventoryItem/Stock not importable.")

        limit = int(opts["limit"])
        biz_id = opts.get("business_id")
        loc_default = opts.get("location_id_default")
        agent_default = opts.get("agent_id_default")
        dry = bool(opts["dry_run"])
        verbose = bool(opts["verbose"])
        do_finalize = bool(opts["finalize"])
        fix_item = bool(opts["fix_item"])

        qs = _manager(InvItem).all()

        if biz_id:
            try:
                qs = qs.filter(models.Q(business_id=biz_id) | models.Q(business__id=biz_id))
            except Exception:
                pass

        # Broad SOLD filter (covers UI flips and legacy fields)
        sold_q = models.Q()
        if _model_has_field(InvItem, "is_sold"):
            sold_q |= models.Q(is_sold=True)
        if _model_has_field(InvItem, "sold_at"):
            sold_q |= models.Q(sold_at__isnull=False)
        if _model_has_field(InvItem, "status"):
            sold_q |= models.Q(status__iexact="sold")
        if _model_has_field(InvItem, "in_stock"):
            sold_q |= models.Q(in_stock=False)
        if _model_has_field(InvItem, "available"):
            sold_q |= models.Q(available=False)
        if _model_has_field(InvItem, "availability"):
            sold_q |= models.Q(availability=False)
        if _model_has_field(InvItem, "quantity"):
            sold_q |= models.Q(quantity__lte=0)
        if _model_has_field(InvItem, "qty"):
            sold_q |= models.Q(qty__lte=0)

        qs = qs.filter(sold_q).order_by("id")

        try:
            j = _joinables(InvItem)
            if j:
                qs = qs.select_related(*j)
        except Exception:
            pass

        qs = qs[:limit]

        scanned = created = skipped_exists = skipped_no_loc = skipped_no_agent = errors = 0
        self.stdout.write(self.style.HTTP_INFO(f"Scanning up to {limit} SOLD items..."))

        # Detect if Sale.location / Sale.agent are NOT NULL on the Sale model
        location_required = False
        agent_required = False
        if _model_has_field(Sale, "location"):
            try:
                f = Sale._meta.get_field("location")  # type: ignore[attr-defined]
                location_required = (getattr(f, "null", True) is False)
            except Exception:
                pass
        if _model_has_field(Sale, "agent"):
            try:
                f = Sale._meta.get_field("agent")  # type: ignore[attr-defined]
                agent_required = (getattr(f, "null", True) is False)
            except Exception:
                pass

        for it in qs:
            scanned += 1
            try:
                if not _is_soldish(it):
                    continue

                if _sale_exists_for_item(it):
                    skipped_exists += 1
                    if verbose:
                        self.stdout.write(f"- skip exists: item #{getattr(it, 'id', None)}")
                    continue

                loc = _resolve_location(it, loc_default)
                ag = _resolve_agent(it, agent_default)

                if location_required and loc is None:
                    skipped_no_loc += 1
                    if verbose:
                        self.stdout.write(f"- skip no location: item #{getattr(it, 'id', None)}")
                    continue

                if agent_required and ag is None:
                    skipped_no_agent += 1
                    if verbose:
                        self.stdout.write(f"- skip no agent: item #{getattr(it, 'id', None)}")
                    continue

                kwargs = {}
                if _model_has_field(Sale, "business"):
                    kwargs["business"] = getattr(it, "business", None)
                for fk in ("inventory_item", "item"):
                    if _model_has_field(Sale, fk):
                        kwargs[fk] = it
                        break
                if _model_has_field(Sale, "product"):
                    kwargs["product"] = getattr(it, "product", None)
                if _model_has_field(Sale, "location") and loc is not None:
                    kwargs["location"] = loc
                if _model_has_field(Sale, "sold_by") and getattr(it, "sold_by", None):
                    kwargs["sold_by"] = getattr(it, "sold_by", None)
                if _model_has_field(Sale, "agent") and ag is not None:
                    kwargs["agent"] = ag
                if _model_has_field(Sale, "sold_at"):
                    kwargs["sold_at"] = _sold_at_from_item(it)

                price = _price_from_item(it)
                for field in ("price", "amount", "sold_price", "total"):
                    if _model_has_field(Sale, field):
                        kwargs[field] = price
                if _model_has_field(Sale, "commission_pct"):
                    kwargs["commission_pct"] = (
                        getattr(it, "commission", None)
                        or getattr(it, "commission_pct", None)
                        or Decimal("0.00")
                    )
                if _model_has_field(Sale, "imei") and getattr(it, "imei", None):
                    kwargs["imei"] = getattr(it, "imei")
                if _model_has_field(Sale, "barcode") and getattr(it, "barcode", None):
                    kwargs["barcode"] = getattr(it, "barcode")

                if verbose:
                    self.stdout.write(
                        f"+ create Sale for item #{getattr(it, 'id', None)} "
                        f"(price={price}, loc={'OK' if loc else 'None'}, agent={'OK' if ag else 'None'})"
                    )

                if not dry:
                    with transaction.atomic():
                        sale = Sale(**{k: v for k, v in kwargs.items() if v is not None})
                        # Let the DB assign defaults/ids, keep side effects minimal
                        setattr(sale, "_skip_finalize", True)  # honored by some codebases
                        sale.save()

                        if fix_item:
                            if _set_item_sold_flags(it):
                                it.save(update_fields=[f.name for f in it._meta.fields])  # type: ignore[attr-defined]

                        if do_finalize and callable(_finalize_sale):
                            try:
                                _finalize_sale(sale)  # type: ignore[misc]
                            except Exception as e:
                                # Don't block the run if finalize fails
                                if verbose:
                                    self.stderr.write(f"  ! finalize failed for sale #{sale.pk}: {e}")

                created += 1

            except Exception as e:
                errors += 1
                if verbose:
                    self.stderr.write(f"! error item #{getattr(it, 'id', None)}: {e}")

        # summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Backfill complete"))
        self.stdout.write(f"  scanned:            {scanned}")
        self.stdout.write(f"  created:            {created}")
        self.stdout.write(f"  skipped (exists):   {skipped_exists}")
        self.stdout.write(f"  skipped (no loc):   {skipped_no_loc}")
        self.stdout.write(f"  skipped (no agent): {skipped_no_agent}")
        self.stdout.write(f"  errors:             {errors}")
        if dry:
            self.stdout.write(self.style.WARNING("Dry run only — nothing was saved."))
