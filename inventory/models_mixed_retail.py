# inventory/models_mixed_retail.py
"""
Mixed Retail vertical models.

Hierarchy: Department → Category → ProductType → Product → Variant

A mixed retail business can sell clothing, electronics, furniture, groceries,
cosmetics, and more — all under one account. No separate modules per product type.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from tenants.models import Business

User = settings.AUTH_USER_MODEL


# ---------------------------------------------------------------------------
# Payment method choices (reused by RetailSale)
# ---------------------------------------------------------------------------

class RetailPaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    AIRTEL_MONEY = "airtel_money", "Airtel Money"
    TNM_MPAMBA = "tnm_mpamba", "TNM Mpamba"
    BANK = "bank", "Bank Transfer"
    CREDIT = "credit", "Credit / Balance"
    OTHER = "other", "Other"


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------

class RetailDepartment(models.Model):
    """
    Top-level grouping. e.g. Electronics, Clothing & Fashion, Furniture, etc.
    Can be seeded (global/shared) or custom (per-business).
    Seeded departments are shared across businesses; business-specific ones are private.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="retail_departments",
        help_text="Null = global seeded department available to all businesses",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    icon = models.CharField(max_length=50, default="bi-bag", blank=True)
    description = models.TextField(blank=True)
    is_seeded = models.BooleanField(default=False, help_text="True = came from seed data")
    is_enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Retail Department"
        verbose_name_plural = "Retail Departments"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class RetailCategory(models.Model):
    """
    Second level under a department. e.g. Smartphones, Laptops, Tablets.
    Can be seeded or custom.
    """
    department = models.ForeignKey(
        RetailDepartment,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="retail_categories",
        help_text="Null = global seeded category",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    description = models.TextField(blank=True)
    is_seeded = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["department__sort_order", "sort_order", "name"]
        verbose_name = "Retail Category"
        verbose_name_plural = "Retail Categories"

    def __str__(self):
        return f"{self.department.name} > {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class RetailProduct(models.Model):
    """
    Inventory product for Mixed Retail.
    Flexible attributes — not every field is required for every product type.
    The department/category determine which fields are relevant.
    """
    UNIT_CHOICES = [
        ("pcs", "Pieces"),
        ("kg", "Kilograms"),
        ("g", "Grams"),
        ("litre", "Litres"),
        ("ml", "Millilitres"),
        ("pair", "Pair"),
        ("pack", "Pack"),
        ("box", "Box"),
        ("roll", "Roll"),
        ("set", "Set"),
        ("m", "Metres"),
        ("other", "Other"),
    ]

    CONDITION_CHOICES = [
        ("new", "New"),
        ("refurbished", "Refurbished"),
        ("used", "Used / Second-hand"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="retail_products",
    )
    department = models.ForeignKey(
        RetailDepartment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    category = models.ForeignKey(
        RetailCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    # Core identity
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, blank=True, help_text="Stock code / barcode")
    brand = models.CharField(max_length=100, blank=True)
    model_number = models.CharField(max_length=100, blank=True)

    # Pricing
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))

    # Stock
    stock_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text="Current quantity in stock",
    )
    reorder_level = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("5"),
        help_text="Alert when stock falls below this level",
    )
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default="pcs")

    # Optional flexible attributes — shown/hidden based on department context
    size = models.CharField(max_length=50, blank=True, help_text="e.g. S, M, L, XL, 42")
    color = models.CharField(max_length=50, blank=True)
    style = models.CharField(max_length=100, blank=True)
    material = models.CharField(max_length=100, blank=True)
    condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, blank=True, default="new",
    )
    dimensions = models.CharField(max_length=100, blank=True, help_text="e.g. 120cm x 80cm x 75cm")

    # Electronics-specific
    serial_number = models.CharField(max_length=100, blank=True)
    imei = models.CharField(max_length=20, blank=True, help_text="IMEI for phones/tablets")
    warranty_months = models.PositiveIntegerField(
        null=True, blank=True, help_text="Warranty period in months",
    )

    # Perishable / batch
    expiry_date = models.DateField(null=True, blank=True, help_text="For food, cosmetics, medicine")
    batch_number = models.CharField(max_length=50, blank=True)

    # Supplier
    supplier_name = models.CharField(max_length=255, blank=True)
    supplier_phone = models.CharField(max_length=20, blank=True)

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_retail_products",
    )

    class Meta:
        ordering = ["department__sort_order", "category__sort_order", "name"]
        verbose_name = "Retail Product"
        verbose_name_plural = "Retail Products"
        indexes = [
            models.Index(fields=["business", "is_active"], name="retail_product_biz_active_idx"),
            models.Index(fields=["business", "department"], name="retail_product_biz_dept_idx"),
        ]

    def __str__(self):
        return self.name

    @property
    def margin(self) -> Decimal:
        if self.selling_price and self.cost_price:
            return self.selling_price - self.cost_price
        return Decimal("0")

    @property
    def margin_pct(self) -> float:
        if self.selling_price and self.selling_price > 0:
            return float(self.margin / self.selling_price * 100)
        return 0.0

    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.reorder_level and self.stock_quantity >= 0

    @property
    def is_out_of_stock(self) -> bool:
        return self.stock_quantity <= 0

    @property
    def stock_value(self) -> Decimal:
        return self.cost_price * self.stock_quantity


# ---------------------------------------------------------------------------
# Retail Sale
# ---------------------------------------------------------------------------

class RetailSale(models.Model):
    """
    A single line-item sale transaction for mixed retail.
    One record per product sold; a basket = multiple RetailSale records with the same receipt_ref.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="retail_sales",
    )
    product = models.ForeignKey(
        RetailProduct,
        on_delete=models.PROTECT,
        related_name="sales",
    )

    # Sale details
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"))
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Actual selling price at time of sale (may differ from product price)",
    )
    cost_price_snapshot = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="Cost price at time of sale — for profit tracking",
    )
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))
    profit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0"))

    payment_method = models.CharField(
        max_length=20,
        choices=RetailPaymentMethod.choices,
        default=RetailPaymentMethod.CASH,
    )

    # Receipt grouping: multiple lines from one transaction share a receipt_ref
    receipt_ref = models.CharField(
        max_length=50, blank=True, db_index=True,
        help_text="Groups multiple sale lines from one transaction",
    )

    # Credit sale fields
    customer_name = models.CharField(max_length=255, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    amount_paid = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True,
        help_text="Amount actually paid (for credit sales)",
    )
    balance_due = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True,
    )
    credit_due_date = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True)
    sold_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_retail_sales",
    )
    is_rolled_back = models.BooleanField(default=False, db_index=True)
    rolled_back_at = models.DateTimeField(null=True, blank=True)
    rollback_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-sold_at"]
        verbose_name = "Retail Sale"
        verbose_name_plural = "Retail Sales"
        indexes = [
            models.Index(fields=["business", "sold_at"], name="retail_sale_biz_time_idx"),
            models.Index(fields=["business", "is_rolled_back"], name="retail_sale_biz_rb_idx"),
        ]

    def __str__(self):
        return f"{self.product.name} × {self.quantity} @ {self.unit_price}"

    def save(self, *args, **kwargs):
        self.total_amount = self.unit_price * self.quantity
        self.profit = (self.unit_price - self.cost_price_snapshot) * self.quantity
        if self.payment_method == RetailPaymentMethod.CREDIT and self.amount_paid is not None:
            self.balance_due = self.total_amount - self.amount_paid
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Business Department Enrollment (per-business enable/disable for global depts)
# ---------------------------------------------------------------------------

class RetailBusinessDepartment(models.Model):
    """
    Tracks whether a specific business has enabled a global seeded department.
    Global (seeded) departments are never toggled globally — each business
    controls its own enabled set via this model.
    """
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="retail_dept_enrollments",
    )
    department = models.ForeignKey(
        RetailDepartment,
        on_delete=models.CASCADE,
        related_name="business_enrollments",
    )
    is_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("business", "department")]
        verbose_name = "Business Department Enrollment"
        verbose_name_plural = "Business Department Enrollments"

    def __str__(self):
        state = "enabled" if self.is_enabled else "disabled"
        return f"{self.business.name} — {self.department.name} ({state})"


# ---------------------------------------------------------------------------
# Product Template (global quick-start suggestions)
# ---------------------------------------------------------------------------

class RetailProductTemplate(models.Model):
    """
    Global product suggestion / quick-start template.
    Merchants browse these and create real RetailProduct records from them.
    No stock quantities or prices — those are set by the merchant.
    """
    department = models.ForeignKey(
        RetailDepartment,
        on_delete=models.CASCADE,
        related_name="product_templates",
    )
    name = models.CharField(max_length=255)
    suggested_unit = models.CharField(
        max_length=20,
        default="pcs",
        help_text="Suggested unit of measure",
    )
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Product Template"
        verbose_name_plural = "Product Templates"

    def __str__(self):
        return f"{self.department.name} › {self.name}"


# ---------------------------------------------------------------------------
# Retail Expense
# ---------------------------------------------------------------------------

class RetailExpense(models.Model):
    """Simple operating expense tracking for mixed retail businesses."""
    CATEGORY_CHOICES = [
        ("rent", "Rent"),
        ("utilities", "Utilities"),
        ("salaries", "Salaries"),
        ("transport", "Transport"),
        ("purchase", "Stock Purchase"),
        ("repairs", "Repairs & Maintenance"),
        ("marketing", "Marketing"),
        ("other", "Other"),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="retail_expenses")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="other")
    description = models.CharField(max_length=255)
    expense_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date"]
        verbose_name = "Retail Expense"

    def __str__(self):
        return f"{self.description} — MWK {self.amount:,.0f}"
