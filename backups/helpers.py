# backups/helpers.py
"""
Helpers for exporting business data to CSV files and ZIP archives.
"""
from __future__ import annotations

import csv
import html
import io
import os
import re
import tempfile
import zipfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.apps import apps
from django.conf import settings
from django.core.files.base import File
from django.core import serializers
from django.db.models import QuerySet, Model, Sum
from django.db import transaction
from django.utils import timezone

from tenants.models import Business


EXPORT_CATEGORY_LABELS = {
    "all": "Everything",
    "inventory": "Inventory Export",
    "financial": "Financial Export",
    "staff": "Staff & HR Export",
    "sales": "Sales Export",
    "wallet": "Wallet Export",
    "reports": "Reports Export",
    "marketplace": "Marketplace Export",
}


EXPORT_SECTIONS = [
    {"key": "business_settings", "category": "reports", "title": "Business Settings", "model": "tenants.Business", "filter": "pk"},
    {"key": "staff_members", "category": "staff", "title": "Staff Records", "model": "tenants.Membership", "filter": "business"},
    {"key": "users", "category": "staff", "title": "Users", "model": settings.AUTH_USER_MODEL, "filter": "member_users"},
    {"key": "locations", "category": "inventory", "title": "Locations", "model": "inventory.Location", "filter": "business"},
    {"key": "inventory_items", "category": "inventory", "title": "Inventory Items", "model": "inventory.InventoryItem", "filter": "business"},
    {"key": "products", "category": "inventory", "title": "Products", "model": "inventory.MerchProduct", "filter": "business"},
    {"key": "stock_movements", "category": "inventory", "title": "Stock Movements", "model": "inventory.StockMovement", "filter": "business"},
    {"key": "purchase_orders", "category": "inventory", "title": "Purchase Orders", "model": "inventory.PurchaseOrder", "filter": "business"},
    {"key": "purchase_order_items", "category": "inventory", "title": "Purchase Order Items", "model": "inventory.PurchaseOrderItem", "filter": "purchase_order__business"},
    {"key": "suppliers", "category": "inventory", "title": "Suppliers", "model": "inventory.Supplier", "filter": "business"},
    {"key": "sales", "category": "sales", "title": "Sales", "model": "sales.Sale", "filter": "location__business"},
    {"key": "layby_orders", "category": "sales", "title": "Layby Orders", "model": "layby.LaybyOrder", "filter": "created_by_id__in"},
    {"key": "layby_payments", "category": "sales", "title": "Layby Payments", "model": "layby.LaybyPayment", "filter": "order__created_by_id__in"},
    {"key": "cash_bank", "category": "financial", "title": "Cash & Bank", "model": "wallet.CashBankTransaction", "filter": "business"},
    {"key": "wallet_transactions", "category": "wallet", "title": "Wallet Records", "model": "wallet.WalletTransaction", "filter": "wallet_scope"},
    {"key": "payslips", "category": "staff", "title": "Payslips", "model": "wallet.Payslip", "filter": "business_or_member_users"},
    {"key": "expenses", "category": "financial", "title": "Expenses & Admin Costs", "model": "wallet.WalletTransaction", "filter": "wallet_costs"},
    {"key": "recurring_costs", "category": "financial", "title": "Recurring Costs", "model": "inventory.RecurringCost", "filter": "business"},
    {"key": "time_logs", "category": "staff", "title": "Time Logs", "model": "timelogs.AgentWorkLog", "filter": "business"},
    {"key": "attendance", "category": "staff", "title": "Attendance", "model": "wallet.AttendanceLog", "filter": "agent_id__in"},
    {"key": "business_health_checks", "category": "reports", "title": "Business Health Checks", "model": "dashboard.BusinessHealthCheck", "filter": "business"},
    {"key": "marketplace_listings", "category": "marketplace", "title": "Marketplace Listings", "model": "inventory.MarketplaceListing", "filter": "seller_business"},
    {"key": "marketplace_orders", "category": "marketplace", "title": "Marketplace Orders", "model": "inventory.MarketplaceOrder", "filter": "seller_business"},
    {"key": "clothing_sales", "category": "sales", "title": "Clothing Sales", "model": "inventory.ClothingSale", "filter": "business"},
    {"key": "liquor_shifts", "category": "sales", "title": "Liquor Shifts", "model": "inventory.LiquorShift", "filter": "business"},
    {"key": "liquor_sales", "category": "sales", "title": "Liquor Sales", "model": "inventory.LiquorSale", "filter": "shift__business"},
    {"key": "liquor_credits", "category": "financial", "title": "Credit Customers & Receivables", "model": "inventory.LiquorCredit", "filter": "sale__shift__business"},
    {"key": "gym_members", "category": "staff", "title": "Gym Members", "model": "inventory.GymMember", "filter": "business"},
    {"key": "pharmacy_batches", "category": "inventory", "title": "Pharmacy Batches", "model": "inventory.PharmacyBatch", "filter": "business"},
    {"key": "pharmacy_sales", "category": "sales", "title": "Pharmacy Sales", "model": "inventory.PharmacySale", "filter": "business"},
    {"key": "car_hire_trips", "category": "sales", "title": "Car Hire Trips", "model": "inventory.CarHireTrip", "filter": "business"},
    {"key": "welding_jobs", "category": "sales", "title": "Welding Jobs", "model": "inventory.WeldingJob", "filter": "business"},
]


FIELD_LABELS = {
    "id": "Record ID",
    "pk": "Record ID",
    "name": "Name",
    "business": "Business",
    "business_kind": "Business Type",
    "created_at": "Created At",
    "updated_at": "Updated At",
    "created_by": "Created By",
    "agent": "Staff Member",
    "user": "User",
    "customer_name": "Customer Name",
    "customer_phone": "Phone",
    "phone": "Phone",
    "email": "Email",
    "amount": "Amount",
    "total_amount": "Total Amount",
    "price": "Price",
    "sell_price": "Selling Price",
    "selling_price": "Selling Price",
    "cost": "Cost",
    "order_price": "Cost Price",
    "cost_price": "Cost Price",
    "profit": "Profit",
    "status": "Status",
    "payment_method": "Payment Method",
    "balance_after": "Balance After",
    "balance_due": "Balance Due",
    "outstanding_balance": "Outstanding Balance",
    "remaining_balance": "Remaining Balance",
    "date": "Date",
    "sold_at": "Sold At",
    "effective_date": "Effective Date",
    "quantity": "Quantity",
    "quantity_in_stock": "Current Stock",
    "sku": "SKU",
    "code": "Code",
    "model": "Model",
    "brand": "Brand",
    "imei": "IMEI",
    "role": "Role",
    "status": "Status",
}

EXCLUDED_FIELD_PATTERNS = (
    "password",
    "token",
    "secret",
    "raw",
    "debug",
    "tmp",
    "session",
    "q1",
    "q2",
)

RESTORE_EXCLUDED_KEYS = {"business_settings", "users", "staff_members"}


def export_queryset_to_csv(queryset: QuerySet, csv_path: Path, fields: List[str] = None) -> int:
    """
    Export a queryset to CSV file.

    Args:
        queryset: Django queryset to export
        csv_path: Path to write CSV file
        fields: List of field names to include (if None, includes all)

    Returns:
        Number of rows exported
    """
    if not queryset.exists():
        # Create empty CSV with headers
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if fields:
                writer.writerow(fields)
        return 0

    # Get model fields
    model = queryset.model
    if not fields:
        fields = [f.name for f in model._meta.get_fields() if not f.many_to_many and not f.one_to_many]

    count = 0
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for obj in queryset.iterator(chunk_size=500):
            row = {}
            for field in fields:
                try:
                    value = getattr(obj, field)
                    # Convert common types to string
                    if hasattr(value, "isoformat"):  # datetime/date
                        row[field] = value.isoformat()
                    elif hasattr(value, "pk"):  # ForeignKey
                        row[field] = value.pk
                    elif value is None:
                        row[field] = ""
                    else:
                        row[field] = str(value)
                except (AttributeError, ValueError):
                    row[field] = ""

            writer.writerow(row)
            count += 1

    return count


def _model_from_path(model_path: str):
    try:
        app_label, model_name = model_path.split(".", 1)
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


def _member_user_ids(business) -> list[int]:
    try:
        from tenants.models import Membership

        return list(Membership.objects.filter(business=business).values_list("user_id", flat=True))
    except Exception:
        return []


def _model_field_names(model) -> set[str]:
    return {getattr(field, "name", "") for field in model._meta.get_fields()}


def _filter_model_for_business(model, business, filter_key: str, member_user_ids: list[int]):
    try:
        qs = model.objects.all()
    except Exception:
        return None

    fields = _model_field_names(model)
    candidates: list[dict[str, Any]] = []
    if filter_key == "pk":
        candidates.append({"pk": business.pk})
    elif filter_key == "member_users":
        candidates.append({"pk__in": member_user_ids})
    elif filter_key in {"created_by_id__in", "agent_id__in", "order__created_by_id__in"}:
        candidates.append({filter_key: member_user_ids})
    elif filter_key == "wallet_scope":
        if "business" in fields:
            candidates.append({"business": business})
        candidates.append({"agent_id__in": member_user_ids})
    elif filter_key == "business_or_member_users":
        if "business" in fields:
            candidates.append({"business": business})
        for key in ("agent_id__in", "employee_id__in", "user_id__in", "created_by_id__in"):
            candidates.append({key: member_user_ids})
    elif filter_key == "wallet_costs":
        if "business" in fields:
            candidates.append({"business": business, "type__in": ["cost_once_off", "cost_recurring"]})
        candidates.append({"agent_id__in": member_user_ids, "type__in": ["cost_once_off", "cost_recurring"]})
    else:
        candidates.append({filter_key: business})

    for candidate in candidates:
        try:
            return qs.filter(**candidate)
        except Exception:
            continue

    for candidate in (
        {"business": business},
        {"seller_business": business},
        {"location__business": business},
        {"shift__business": business},
        {"work_log__business": business},
        {"member__business": business},
        {"product__business": business},
        {"order__business": business},
        {"purchase_order__business": business},
    ):
        try:
            return qs.filter(**candidate)
        except Exception:
            continue
    return None


def _professional_label(field_name: str) -> str:
    if field_name in FIELD_LABELS:
        return FIELD_LABELS[field_name]
    label = re.sub(r"_id$", "", field_name)
    label = label.replace("_", " ").strip().title()
    return label or field_name


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "export").strip("_")
    return cleaned[:80] or "export"


def _exportable_fields(model) -> list:
    fields = []
    for field in model._meta.get_fields():
        if field.many_to_many or field.one_to_many:
            continue
        name = getattr(field, "name", "")
        lowered = name.lower()
        if any(pattern in lowered for pattern in EXCLUDED_FIELD_PATTERNS):
            continue
        if name.endswith("_ptr"):
            continue
        fields.append(field)
    return fields


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "get_full_name") and callable(value.get_full_name):
        full_name = value.get_full_name()
        if full_name:
            return full_name
    return str(value)


def _rows_for_queryset(qs) -> tuple[list[str], list[list[str]]]:
    fields = _exportable_fields(qs.model)
    headers = [_professional_label(field.name) for field in fields]
    rows: list[list[str]] = []
    for obj in qs.iterator(chunk_size=500):
        row = []
        for field in fields:
            try:
                value = getattr(obj, field.name)
            except Exception:
                value = ""
            row.append(_format_value(value))
        rows.append(row)
    return headers, rows


def build_export_sections(business: Business, category: str = "all", *, include_rows: bool = True) -> list[dict[str, Any]]:
    member_user_ids = _member_user_ids(business)
    sections: list[dict[str, Any]] = []
    for item in EXPORT_SECTIONS:
        if category != "all" and item["category"] != category:
            continue
        model = _model_from_path(item["model"])
        if model is None:
            continue
        qs = _filter_model_for_business(model, business, item["filter"], member_user_ids)
        if qs is None:
            continue
        try:
            qs = qs.order_by("pk")
        except Exception:
            pass
        try:
            count = qs.count()
        except Exception:
            count = 0
        if include_rows:
            headers, rows = _rows_for_queryset(qs)
        else:
            headers, rows = [], []
        sections.append(
            {
                "key": item["key"],
                "category": item["category"],
                "title": item["title"],
                "filename": f"{item['key']}.csv",
                "headers": headers,
                "rows": rows,
                "count": count,
                "model": item["model"],
            }
        )
    return sections


def build_export_summary(business: Business, category: str = "all", *, include_rows: bool = True) -> dict[str, Any]:
    sections = build_export_sections(business, category, include_rows=include_rows)
    records_count = {section["key"]: section["count"] for section in sections}
    return {
        "sections": sections,
        "records_count": records_count,
        "total_records": sum(records_count.values()),
        "section_count": len(sections),
    }


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def create_export_zip_path(business: Business, category: str = "all") -> tuple[Path, Dict[str, int]]:
    temp_dir = Path(tempfile.mkdtemp(prefix="data_vault_"))
    summary = build_export_summary(business, category)
    records_count = summary["records_count"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{_safe_filename(business.name)}_{category}_data_vault_{timestamp}.zip"
    zip_path = temp_dir / filename

    try:
        for section in summary["sections"]:
            _write_csv(temp_dir / section["filename"], section["headers"], section["rows"])

        readme = temp_dir / "README.txt"
        with open(readme, "w", encoding="utf-8") as f:
            f.write("Emajinet Business Data Vault\n")
            f.write("============================\n\n")
            f.write("Your data belongs to you.\n")
            f.write("Download everything anytime. Your business records are always yours.\n\n")
            f.write(f"Business: {business.name}\n")
            f.write(f"Category: {EXPORT_CATEGORY_LABELS.get(category, category.title())}\n")
            f.write(f"Generated: {timezone.now().isoformat()}\n")
            f.write(f"Total records: {summary['total_records']:,}\n\n")
            f.write("Files included:\n")
            for section in summary["sections"]:
                f.write(f"- {section['filename']}: {section['title']} ({section['count']:,} records)\n")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for csv_file in temp_dir.glob("*.csv"):
                zipf.write(csv_file, csv_file.name)
            zipf.write(readme, readme.name)
            if category == "all":
                fixture_json = build_restore_fixture_json(business)
                zipf.writestr("restore/fixture.json", fixture_json)
                zipf.writestr(
                    "restore/manifest.txt",
                    "This fixture is used by Emajinet's guarded restore workflow.\n"
                    "Business/user/membership records are not overwritten automatically.\n",
                )

        return zip_path, records_count
    except Exception:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _restore_sections(business: Business) -> list[tuple[dict[str, Any], Any]]:
    member_user_ids = _member_user_ids(business)
    sections = []
    for item in EXPORT_SECTIONS:
        if item["key"] in RESTORE_EXCLUDED_KEYS:
            continue
        model = _model_from_path(item["model"])
        if model is None:
            continue
        qs = _filter_model_for_business(model, business, item["filter"], member_user_ids)
        if qs is None:
            continue
        try:
            qs = qs.order_by("pk")
        except Exception:
            pass
        sections.append((item, qs))
    return sections


def build_restore_fixture_json(business: Business) -> str:
    objects = []
    for _item, qs in _restore_sections(business):
        try:
            objects.extend(list(qs))
        except Exception:
            continue
    return serializers.serialize("json", objects, use_natural_foreign_keys=False, use_natural_primary_keys=False)


def snapshot_has_restore_fixture(snapshot) -> bool:
    try:
        with snapshot.file.open("rb") as fh:
            with zipfile.ZipFile(fh) as zf:
                return "restore/fixture.json" in zf.namelist()
    except Exception:
        return False


def restore_business_from_snapshot(snapshot, business: Business) -> int:
    if not snapshot_has_restore_fixture(snapshot):
        raise ValueError("This snapshot does not contain a restore fixture. Download it manually or create a fresh snapshot first.")

    with snapshot.file.open("rb") as fh:
        with zipfile.ZipFile(fh) as zf:
            fixture_json = zf.read("restore/fixture.json").decode("utf-8")

    objects = list(serializers.deserialize("json", fixture_json))
    sections = _restore_sections(business)
    restored = 0

    with transaction.atomic():
        for _item, qs in reversed(sections):
            try:
                qs.delete()
            except Exception:
                continue

        for obj in objects:
            model = obj.object.__class__
            fields = _model_field_names(model)
            if "business" in fields:
                setattr(obj.object, "business", business)
            elif "seller_business" in fields:
                setattr(obj.object, "seller_business", business)
            obj.save()
            restored += 1

    return restored


def _xml_cell(value: Any) -> str:
    text = html.escape(_format_value(value))
    return f'<c t="inlineStr"><is><t>{text}</t></is></c>'


def _sheet_xml(headers: list[str], rows: list[list[str]]) -> str:
    sheet_rows = []
    all_rows = [headers] + rows
    for idx, row in enumerate(all_rows, start=1):
        cells = "".join(_xml_cell(value) for value in row)
        sheet_rows.append(f'<row r="{idx}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )


def create_export_xlsx_bytes(business: Business, category: str = "all") -> tuple[bytes, Dict[str, int]]:
    summary = build_export_summary(business, category)
    output = io.BytesIO()
    sections = summary["sections"] or [
        {"title": "No Data", "headers": ["Message"], "rows": [["No data for this export."]], "count": 0, "key": "no_data"}
    ]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i, _section in enumerate(sections, start=1)
            )
            + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>",
        )
        sheets_xml = []
        rels_xml = []
        for i, section in enumerate(sections, start=1):
            sheet_name = html.escape(section["title"][:31] or f"Sheet {i}")
            sheets_xml.append(f'<sheet name="{sheet_name}" sheetId="{i}" r:id="rId{i}"/>')
            rels_xml.append(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            )
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(section["headers"], section["rows"]))
        zf.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(sheets_xml)
            + "</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(rels_xml)
            + "</Relationships>",
        )
        zf.writestr("docProps/core.xml", f"<coreProperties><title>{html.escape(business.name)} Data Vault</title></coreProperties>")
        zf.writestr("docProps/app.xml", "<Properties><Application>Emajinet</Application></Properties>")
    return output.getvalue(), summary["records_count"]


def build_executive_summary(business: Business) -> dict[str, Any]:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    data: dict[str, Any] = {
        "stock_value": Decimal("0.00"),
        "total_sales": Decimal("0.00"),
        "total_profit": Decimal("0.00"),
        "receivables": Decimal("0.00"),
        "cash_balance": Decimal("0.00"),
        "expenses": Decimal("0.00"),
        "books_balance": None,
        "health_check": None,
    }
    try:
        from dashboard.services_health import _sales_totals

        totals = _sales_totals(business, month_start, today)
        data["total_sales"] = totals.get("revenue") or Decimal("0.00")
        data["total_profit"] = (totals.get("revenue") or Decimal("0.00")) - (totals.get("cost") or Decimal("0.00"))
    except Exception:
        pass
    try:
        from dashboard.services_books_balance import _current_stock_value, _receivables_for_business, run_daily_books_balance

        data["stock_value"] = _current_stock_value(business)
        data["receivables"] = _receivables_for_business(business)[0]
        data["books_balance"] = run_daily_books_balance(business)
        data["health_check"] = data["books_balance"]
    except Exception:
        pass
    try:
        from wallet.models import CashBankTransaction

        rows = CashBankTransaction.objects.filter(business=business, date__lte=today)
        ins = rows.filter(direction=CashBankTransaction.Direction.CASH_IN).aggregate(s=Sum("amount")).get("s") or 0
        outs = rows.filter(direction=CashBankTransaction.Direction.CASH_OUT).aggregate(s=Sum("amount")).get("s") or 0
        data["cash_balance"] = Decimal(ins) - Decimal(outs)
        data["expenses"] = rows.filter(direction=CashBankTransaction.Direction.CASH_OUT, date__gte=month_start).aggregate(s=Sum("amount")).get("s") or Decimal("0.00")
    except Exception:
        pass
    return data


def export_business_data_to_zip(business: Business) -> tuple[Path, Dict[str, int]]:
    """
    Export all data for a business to a ZIP file.

    Args:
        business: Business instance to export

    Returns:
        Tuple of (zip_file_path, records_count_dict)

    Raises:
        Exception: If export fails
    """
    return create_export_zip_path(business, "all")

    # Create temp directory for CSV files
    temp_dir = Path(tempfile.mkdtemp(prefix="backup_"))
    records_count = {}

    try:
        # ============================================================
        # CORE BUSINESS DATA
        # ============================================================

        # Business info
        from tenants.models import Business, Membership

        business_data = Business.objects.filter(pk=business.pk)
        count = export_queryset_to_csv(
            business_data, temp_dir / "business.csv", ["id", "name", "business_kind", "created_at"]
        )
        records_count["business"] = count

        # Memberships (users in this business)
        memberships = Membership.objects.filter(business=business)
        count = export_queryset_to_csv(
            memberships, temp_dir / "memberships.csv", ["id", "user_id", "business_id", "role", "status", "joined_at"]
        )
        records_count["memberships"] = count

        # Locations
        from inventory.models import Location

        locations = Location.objects.filter(business=business)
        count = export_queryset_to_csv(
            locations, temp_dir / "locations.csv", ["id", "name", "city", "latitude", "longitude", "is_default"]
        )
        records_count["locations"] = count

        # ============================================================
        # INVENTORY DATA
        # ============================================================

        # Phone inventory items
        from inventory.models import InventoryItem

        inventory = InventoryItem.objects.filter(business=business)
        count = export_queryset_to_csv(
            inventory,
            temp_dir / "inventory_items.csv",
            [
                "id",
                "imei",
                "brand",
                "model",
                "cost",
                "sell_price",
                "status",
                "scanned_at",
                "sold_at",
                "location_id",
                "payment_method",
            ],
        )
        records_count["inventory_items"] = count

        # MerchProduct (non-phone products)
        from inventory.models import MerchProduct

        products = MerchProduct.objects.filter(business=business)
        count = export_queryset_to_csv(
            products,
            temp_dir / "merch_products.csv",
            ["id", "sku", "name", "category", "cost", "sell_price", "created_at"],
        )
        records_count["merch_products"] = count

        # ============================================================
        # SALES DATA
        # ============================================================

        # Phone sales
        from sales.models import Sale

        sales = Sale.objects.filter(location__business=business)
        count = export_queryset_to_csv(
            sales,
            temp_dir / "sales.csv",
            [
                "id",
                "item_id",
                "agent_id",
                "location_id",
                "sold_at",
                "price",
                "commission_pct",
                "payment_method",
                "created_at",
            ],
        )
        records_count["sales"] = count

        # ============================================================
        # WALLET DATA
        # ============================================================

        from wallet.models import WalletTransaction

        # Get all transactions for users who are members of this business
        member_user_ids = memberships.values_list("user_id", flat=True)
        wallet_txns = WalletTransaction.objects.filter(agent_id__in=member_user_ids)
        count = export_queryset_to_csv(
            wallet_txns,
            temp_dir / "wallet_transactions.csv",
            [
                "id",
                "ledger",
                "agent_id",
                "type",
                "amount",
                "note",
                "reference",
                "effective_date",
                "created_at",
                "created_by_id",
            ],
        )
        records_count["wallet_transactions"] = count

        # ============================================================
        # TIMELOGS DATA
        # ============================================================

        from timelogs.models import AgentWorkLog, LocationPing

        work_logs = AgentWorkLog.objects.filter(business=business)
        count = export_queryset_to_csv(
            work_logs,
            temp_dir / "work_logs.csv",
            [
                "id",
                "agent_id",
                "business_id",
                "location_id",
                "work_date",
                "first_seen_at",
                "last_seen_at",
                "total_on_site_minutes",
                "total_idle_minutes",
                "penalty_amount",
                "bonus_amount",
            ],
        )
        records_count["work_logs"] = count

        # Location pings (optional - can be large)
        pings = LocationPing.objects.filter(work_log__business=business)
        count = export_queryset_to_csv(
            pings,
            temp_dir / "location_pings.csv",
            ["id", "work_log_id", "timestamp", "latitude", "longitude", "is_inside_geofence"],
        )
        records_count["location_pings"] = count

        # ============================================================
        # LAYBY DATA
        # ============================================================

        try:
            from layby.models import LaybyOrder, LaybyPayment

            # Layby orders created by members of this business
            layby_orders = LaybyOrder.objects.filter(created_by_id__in=member_user_ids)
            count = export_queryset_to_csv(
                layby_orders,
                temp_dir / "layby_orders.csv",
                [
                    "id",
                    "ref",
                    "customer_name",
                    "customer_phone",
                    "id_number",
                    "item_name",
                    "sku",
                    "total_price",
                    "deposit_amount",
                    "status",
                    "created_at",
                    "created_by_id",
                ],
            )
            records_count["layby_orders"] = count

            # Layby payments
            layby_payments = LaybyPayment.objects.filter(order__in=layby_orders)
            count = export_queryset_to_csv(
                layby_payments,
                temp_dir / "layby_payments.csv",
                ["id", "order_id", "amount", "method", "tx_ref", "received_at", "received_by_id"],
            )
            records_count["layby_payments"] = count
        except Exception:
            # Layby might not be installed
            pass

        # ============================================================
        # VERTICAL-SPECIFIC DATA
        # ============================================================

        # LIQUOR
        try:
            from inventory.models_verticals import (
                LiquorShift,
                LiquorShiftStock,
                LiquorSale,
                LiquorCredit,
                LiquorCreditPayment,
            )

            liquor_shifts = LiquorShift.objects.filter(business=business)
            count = export_queryset_to_csv(
                liquor_shifts,
                temp_dir / "liquor_shifts.csv",
                [
                    "id",
                    "business_id",
                    "location_id",
                    "barman_id",
                    "started_at",
                    "ended_at",
                    "status",
                    "total_sales_amount",
                    "total_profit_amount",
                ],
            )
            records_count["liquor_shifts"] = count

            stock = LiquorShiftStock.objects.filter(shift__business=business)
            count = export_queryset_to_csv(
                stock,
                temp_dir / "liquor_shift_stock.csv",
                [
                    "id",
                    "shift_id",
                    "product_id",
                    "opening_bottles",
                    "closing_bottles",
                    "bottles_sold",
                    "bottles_count",
                    "variance",
                ],
            )
            records_count["liquor_shift_stock"] = count

            sales = LiquorSale.objects.filter(shift__business=business)
            count = export_queryset_to_csv(
                sales,
                temp_dir / "liquor_sales.csv",
                [
                    "id",
                    "shift_id",
                    "product_id",
                    "unit_type",
                    "quantity",
                    "price_per_unit",
                    "total_amount",
                    "sale_type",
                    "sold_at",
                ],
            )
            records_count["liquor_sales"] = count

            credits = LiquorCredit.objects.filter(sale__shift__business=business)
            count = export_queryset_to_csv(
                credits,
                temp_dir / "liquor_credits.csv",
                ["id", "sale_id", "customer_name", "customer_phone", "amount", "amount_paid", "status", "created_at"],
            )
            records_count["liquor_credits"] = count

            credit_payments = LiquorCreditPayment.objects.filter(credit__sale__shift__business=business)
            count = export_queryset_to_csv(
                credit_payments,
                temp_dir / "liquor_credit_payments.csv",
                [
                    "id",
                    "credit_id",
                    "amount",
                    "payment_method",
                    "transaction_id",
                    "submitted_at",
                    "submitted_by_id",
                    "status",
                ],
            )
            records_count["liquor_credit_payments"] = count
        except Exception:
            # Liquor models might not be available
            pass

        # GYM
        try:
            from inventory.models_verticals import GymMember, GymMemberPayment

            gym_members = GymMember.objects.filter(business=business)
            count = export_queryset_to_csv(
                gym_members,
                temp_dir / "gym_members.csv",
                [
                    "id",
                    "business_id",
                    "name",
                    "phone",
                    "id_number",
                    "membership_type",
                    "monthly_fee",
                    "status",
                    "joined_at",
                    "last_payment_date",
                ],
            )
            records_count["gym_members"] = count

            payments = GymMemberPayment.objects.filter(member__business=business)
            count = export_queryset_to_csv(
                payments,
                temp_dir / "gym_payments.csv",
                [
                    "id",
                    "member_id",
                    "amount",
                    "payment_method",
                    "period_start",
                    "period_end",
                    "paid_at",
                    "received_by_id",
                ],
            )
            records_count["gym_payments"] = count
        except Exception:
            pass

        # CLOTHING
        try:
            from inventory.models_verticals import ClothingSale

            clothing_sales = ClothingSale.objects.filter(business=business)
            count = export_queryset_to_csv(
                clothing_sales,
                temp_dir / "clothing_sales.csv",
                [
                    "id",
                    "business_id",
                    "product_id",
                    "quantity",
                    "unit_price",
                    "total_amount",
                    "payment_method",
                    "sold_at",
                    "sold_by_id",
                ],
            )
            records_count["clothing_sales"] = count
        except Exception:
            pass

        # PHARMACY
        try:
            from inventory.models_pharmacy import PharmacyBatch, PharmacySale

            batches = PharmacyBatch.objects.filter(business=business)
            count = export_queryset_to_csv(
                batches,
                temp_dir / "pharmacy_batches.csv",
                ["id", "business_id", "product_id", "batch_number", "quantity", "expiry_date", "received_at"],
            )
            records_count["pharmacy_batches"] = count

            pharmacy_sales = PharmacySale.objects.filter(business=business)
            count = export_queryset_to_csv(
                pharmacy_sales,
                temp_dir / "pharmacy_sales.csv",
                [
                    "id",
                    "business_id",
                    "product_id",
                    "batch_id",
                    "quantity",
                    "unit_price",
                    "total_amount",
                    "sold_at",
                    "sold_by_id",
                ],
            )
            records_count["pharmacy_sales"] = count
        except Exception:
            pass

        # ============================================================
        # CREATE ZIP FILE
        # ============================================================

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"backup_{business.name}_{timestamp}.zip".replace(" ", "_")
        zip_path = temp_dir / zip_filename

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add all CSV files
            for csv_file in temp_dir.glob("*.csv"):
                zipf.write(csv_file, csv_file.name)

            # Add metadata file
            metadata_path = temp_dir / "backup_metadata.txt"
            with open(metadata_path, "w") as f:
                f.write(f"CircuitCity Data Backup\n")
                f.write(f"========================\n\n")
                f.write(f"Business: {business.name}\n")
                f.write(f"Business ID: {business.pk}\n")
                f.write(f"Business Type: {business.business_kind}\n")
                f.write(f"Generated: {timezone.now().isoformat()}\n\n")
                f.write(f"Records Count:\n")
                for model, count in sorted(records_count.items()):
                    f.write(f"  {model}: {count:,}\n")

            zipf.write(metadata_path, "backup_metadata.txt")

        return zip_path, records_count

    except Exception as e:
        # Clean up temp directory on error
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
        raise e


def cleanup_temp_files(zip_path: Path) -> None:
    """Clean up temporary files after backup."""
    import shutil

    if zip_path and zip_path.parent.name.startswith("backup_"):
        shutil.rmtree(zip_path.parent, ignore_errors=True)
