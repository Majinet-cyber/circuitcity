from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from django.utils import timezone


MONEY_PLACES = Decimal("0.01")
PERCENT_BASE = Decimal("100")

DEFAULT_PAYMENT_MILESTONES = (
    {"key": "deposit", "label": "Deposit", "percent": Decimal("50")},
    {"key": "progress", "label": "Fabrication progress", "percent": Decimal("25")},
    {"key": "completion", "label": "Completion / delivery", "percent": Decimal("25")},
)


def to_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError):
        return default


def quantize_money(value) -> Decimal:
    return to_decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def clamp_percent(value, default: Decimal = Decimal("0")) -> Decimal:
    percent = to_decimal(value, default)
    if percent < 0:
        return Decimal("0")
    if percent > 100:
        return Decimal("100")
    return percent


def format_percent(value, default: Decimal = Decimal("0")) -> str:
    percent = clamp_percent(value, default)
    if percent == percent.to_integral_value():
        return str(int(percent))
    text = format(percent.normalize(), "f")
    return text.rstrip("0").rstrip(".") or "0"


def default_payment_milestones() -> list[dict[str, str]]:
    return [
        {"key": item["key"], "label": item["label"], "percent": str(item["percent"])}
        for item in DEFAULT_PAYMENT_MILESTONES
    ]


def normalize_payment_milestones(raw: Iterable[dict] | None = None) -> list[dict[str, str]]:
    if not raw:
        return default_payment_milestones()

    milestones: list[dict[str, str]] = []
    total = Decimal("0")
    for index, item in enumerate(raw, start=1):
        label = str(item.get("label") or f"Milestone {index}").strip()[:80]
        percent = clamp_percent(item.get("percent"))
        if percent <= 0:
            continue
        total += percent
        milestones.append(
            {
                "key": str(item.get("key") or f"milestone_{index}")[:40],
                "label": label,
                "percent": format_percent(percent),
            }
        )

    if not milestones or total != PERCENT_BASE:
        return default_payment_milestones()
    return milestones


def payment_milestones_from_post(post) -> list[dict[str, str]]:
    return normalize_payment_milestones(
        [
            {"key": "deposit", "label": post.get("milestone_1_label") or "Deposit", "percent": post.get("milestone_1_percent")},
            {"key": "progress", "label": post.get("milestone_2_label") or "Fabrication progress", "percent": post.get("milestone_2_percent")},
            {"key": "completion", "label": post.get("milestone_3_label") or "Completion / delivery", "percent": post.get("milestone_3_percent")},
        ]
    )


def quote_specs_with_customer_details(post) -> dict:
    return {
        "customer_address": (post.get("customer_address") or "").strip(),
        "payment_details": (post.get("payment_details") or "").strip(),
    }


def quote_finance_metadata(post) -> dict:
    return {
        "payment_milestones": payment_milestones_from_post(post),
        "payment_details": (post.get("payment_details") or "").strip(),
    }


def apply_line_adjustments(quantity, unit_price=None, waste_percent=0, discount_percent=0):
    quantity_dec = to_decimal(quantity, Decimal("1"))
    waste = clamp_percent(waste_percent)
    discount = clamp_percent(discount_percent)

    adjusted_quantity = (quantity_dec * (Decimal("1") + waste / PERCENT_BASE)).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )

    unit_price_dec = None
    if unit_price not in (None, ""):
        unit_price_dec = to_decimal(unit_price)
        unit_price_dec = (unit_price_dec * (Decimal("1") - discount / PERCENT_BASE)).quantize(
            MONEY_PLACES,
            rounding=ROUND_HALF_UP,
        )

    adjustment_notes = []
    if waste:
        adjustment_notes.append(f"Waste allowance {format_percent(waste)}%")
    if discount:
        adjustment_notes.append(f"Discount {format_percent(discount)}%")
    return adjusted_quantity, unit_price_dec, adjustment_notes


def append_adjustment_notes(notes: str, adjustment_notes: list[str]) -> str:
    base = (notes or "").strip()
    suffix = "; ".join(adjustment_notes)
    if base and suffix:
        return f"{base} ({suffix})"[:255]
    return (base or suffix)[:255]


def quote_totals(quote) -> dict[str, Decimal]:
    line_items = quote.line_items.all()
    costs = quote.costs.all()

    materials_total = sum((item.line_total for item in line_items), Decimal("0"))
    labour_total = sum((cost.amount for cost in costs if cost.cost_type == "labour"), Decimal("0"))
    transport_total = sum((cost.amount for cost in costs if cost.cost_type == "transport"), Decimal("0"))
    other_total = sum((cost.amount for cost in costs if cost.cost_type == "other"), Decimal("0"))
    profit_total = sum((cost.amount for cost in costs if cost.cost_type == "profit"), Decimal("0"))
    subtotal = materials_total + labour_total + transport_total + other_total
    total = subtotal + profit_total

    return {
        "materials_total": quantize_money(materials_total),
        "labour_total": quantize_money(labour_total),
        "transport_total": quantize_money(transport_total),
        "other_total": quantize_money(other_total),
        "profit_total": quantize_money(profit_total),
        "subtotal": quantize_money(subtotal),
        "grand_total": quantize_money(total),
    }


def sync_quote_totals(quote):
    totals = quote_totals(quote)
    quote.materials_cost = totals["materials_total"]
    quote.labour_cost = totals["labour_total"]
    quote.overhead_cost = totals["transport_total"] + totals["other_total"]
    quote.subtotal = totals["subtotal"]
    quote.total = totals["grand_total"]
    quote.min_price = totals["subtotal"]

    cost_breakdown = dict(quote.cost_breakdown or {})
    cost_breakdown.update(
        {
            "materials": str(totals["materials_total"]),
            "labour": str(totals["labour_total"]),
            "transport": str(totals["transport_total"]),
            "other": str(totals["other_total"]),
            "profit": str(totals["profit_total"]),
            "subtotal": str(totals["subtotal"]),
            "total": str(totals["grand_total"]),
            "payment_milestones": cost_breakdown.get("payment_milestones") or default_payment_milestones(),
        }
    )
    quote.cost_breakdown = cost_breakdown
    quote.save(
        update_fields=[
            "materials_cost",
            "labour_cost",
            "overhead_cost",
            "subtotal",
            "total",
            "min_price",
            "cost_breakdown",
            "updated_at",
        ]
    )
    return totals


def quote_bom_snapshot(quote) -> list[dict[str, str]]:
    return [
        {
            "material_name": item.material_name,
            "material_unit": item.material_unit,
            "quantity": str(item.quantity),
            "unit_price_mwk": str(item.unit_price or Decimal("0")),
            "line_total_mwk": str(item.line_total),
            "notes": item.notes,
        }
        for item in quote.line_items.all()
    ]


def build_invoice_line_items_from_quote(quote) -> list[dict[str, str]]:
    line_items = [
        {
            "description": item.material_name,
            "quantity": str(item.quantity),
            "unit_price": str(item.unit_price or Decimal("0")),
            "total": str(item.line_total),
        }
        for item in quote.line_items.all()
    ]
    for cost in quote.costs.all():
        line_items.append(
            {
                "description": cost.description or cost.get_cost_type_display(),
                "quantity": "1",
                "unit_price": str(cost.amount),
                "total": str(cost.amount),
            }
        )
    return line_items


def quote_payment_milestones(quote) -> list[dict[str, str]]:
    metadata = quote.cost_breakdown or {}
    return normalize_payment_milestones(metadata.get("payment_milestones"))


def payment_terms_text(quote) -> str:
    milestones = quote_payment_milestones(quote)
    return "; ".join(f"{format_percent(item['percent'])}% {item['label']}" for item in milestones)


def record_invoice_payment(invoice, amount, paid_on=None):
    from inventory.models_welding import WeldingInvoiceStatus

    payment_amount = quantize_money(amount)
    if payment_amount <= 0:
        raise ValueError("Payment amount must be greater than 0")

    invoice.amount_paid = min(quantize_money(invoice.amount_paid + payment_amount), quantize_money(invoice.total))
    invoice.paid_date = paid_on or timezone.now().date()
    if invoice.amount_paid >= invoice.total:
        invoice.status = WeldingInvoiceStatus.PAID
    elif invoice.amount_paid > 0:
        invoice.status = WeldingInvoiceStatus.PARTIAL
    invoice.save(update_fields=["amount_paid", "paid_date", "status", "updated_at"])
    return invoice
