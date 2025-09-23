# inventory/views_import.py
import csv, io
from decimal import Decimal, InvalidOperation
from datetime import datetime as dt

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.utils import timezone

from .models import Product, Location, InventoryItem
from .forms import CSVImportForm
from .utils import user_in_group, ADMIN  # <-- fixed


def _to_decimal(val, default=Decimal("0")) -> Decimal:
    if val in (None, ""):
        return default
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return default


@login_required
def import_opening_stock(request):
    """
    Required headers: product_code, product_name, location, quantity
    Optional: serial_or_imei, cost_price, sale_price, received_at(YYYY-MM-DD)
    """
    if not user_in_group(request.user, ADMIN):
        raise PermissionDenied("Only Admin can import data.")

    if request.method == "POST":
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            raw = form.cleaned_data["csv_file"].read().decode("utf-8", errors="ignore")
            reader = csv.DictReader(io.StringIO(raw))
            required = {"product_code","product_name","location","quantity"}
            headers = {(h or "").strip() for h in (reader.fieldnames or [])}
            missing = required - headers
            if missing:
                messages.error(request, f"Missing required columns: {', '.join(sorted(missing))}")
                return redirect("import_opening_stock")

            create_missing = form.cleaned_data["create_missing_products"]
            max_expand = int(getattr(settings, "DATA_IMPORT_MAX_EXPANSION", 5000))

            to_create = []
            today = timezone.localdate()

            with transaction.atomic():
                for i, row in enumerate(reader, start=2):
                    try:
                        code = (row.get("product_code") or "").strip()
                        name = (row.get("product_name") or "").strip()
                        loc_name = (row.get("location") or "").strip()
                        qty = int((row.get("quantity") or "0").strip() or 0)
                        imei = (row.get("serial_or_imei") or "").strip()
                        cost = _to_decimal(row.get("cost_price"))
                        price = _to_decimal(row.get("sale_price"))
                        rcv = (row.get("received_at") or "").strip()
                        received_at = today
                        if rcv:
                            try:
                                received_at = dt.strptime(rcv, "%Y-%m-%d").date()
                            except Exception:
                                received_at = today

                        if not code or not name or not loc_name:
                            raise ValueError("product_code, product_name, and location are required")

                        # Product
                        try:
                            prod = Product.objects.get(code=code)
                            touched = False
                            if cost and prod.cost_price != cost:
                                prod.cost_price = cost; touched = True
                            if price and prod.sale_price != price:
                                prod.sale_price = price; touched = True
                            if name and not prod.name:
                                prod.name = name; touched = True
                            if touched:
                                prod.save(update_fields=["cost_price","sale_price","name"])
                        except Product.DoesNotExist:
                            if not create_missing:
                                raise ValueError(f"Unknown product_code '{code}'")
                            prod = Product.objects.create(
                                code=code,
                                name=name,
                                brand="",
                                model=name or code,
                                variant="",
                                cost_price=cost,
                                sale_price=price,
                            )

                        # Location
                        loc, _ = Location.objects.get_or_create(name=loc_name)

                        # Create items
                        if imei:
                            to_create.append(InventoryItem(
                                product=prod,
                                imei=imei,
                                current_location=loc,
                                status="IN_STOCK",
                                received_at=received_at,
                                order_price=cost,
                                selling_price=price if price > 0 else None,
                            ))
                        else:
                            if qty < 0:
                                raise ValueError("quantity cannot be negative")
                            if qty > max_expand:
                                raise ValueError(f"quantity too large ({qty} > {max_expand})")
                            for _ in range(qty):
                                to_create.append(InventoryItem(
                                    product=prod,
                                    current_location=loc,
                                    status="IN_STOCK",
                                    received_at=received_at,
                                    order_price=cost,
                                    selling_price=price if price > 0 else None,
                                ))

                    except Exception as e:
                        raise ValueError(f"Import error at line {i}: {e}") from e

                if to_create:
                    InventoryItem.objects.bulk_create(to_create, batch_size=1000)

            messages.success(request, f"Imported {len(to_create)} inventory units.")
            return redirect("inventory:inventory_dashboard")
    else:
        form = CSVImportForm()

    return render(request, "inventory/import_opening_stock.html", {"form": form})
