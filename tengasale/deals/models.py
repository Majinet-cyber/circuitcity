from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class DeviceBrand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    logo = models.ImageField(upload_to="brand_logos/", blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class DeviceDeal(models.Model):
    brand = models.ForeignKey(DeviceBrand, on_delete=models.CASCADE, related_name="deals")
    model_name = models.CharField(max_length=120)
    specs = models.CharField(max_length=80)

    cash_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    min_cash_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_cash_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    default_cash_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deposit_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=13,
        validators=[MinValueValidator(Decimal("13")), MaxValueValidator(Decimal("16"))],
    )
    loan_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("2.5"))
    term_months = models.PositiveIntegerField(default=12)
    unlock_days = models.PositiveIntegerField(default=7)

    total_12_month_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def calculated_total_loan(self, cash_price=None):
        selected_price = Decimal(cash_price) if cash_price is not None else self.default_cash_price
        return round(selected_price * self.loan_multiplier, 2)

    def calculated_deposit(self, cash_price=None):
        total_loan = self.calculated_total_loan(cash_price)
        return round((total_loan * self.deposit_percent) / Decimal("100"), 2)

    def calculated_monthly_payment(self, cash_price=None):
        total_loan = self.calculated_total_loan(cash_price)
        return round(total_loan / Decimal(self.term_months), 2)

    def calculated_daily_payment(self, cash_price=None):
        total_loan = self.calculated_total_loan(cash_price)
        return round(total_loan / Decimal(self.term_months * 30), 2)

    def calculated_6_month_total(self, cash_price=None):
        return round(self.calculated_total_loan(cash_price) * Decimal("0.85"), 2)

    def calculated_6_month_monthly(self, cash_price=None):
        return round(self.calculated_6_month_total(cash_price) / Decimal("6"), 2)

    def calculated_6_month_daily(self, cash_price=None):
        return round(self.calculated_6_month_total(cash_price) / Decimal("180"), 2)

    def calculated_3_month_total(self, cash_price=None):
        return round(self.calculated_total_loan(cash_price) * Decimal("0.75"), 2)

    def calculated_3_month_monthly(self, cash_price=None):
        return round(self.calculated_3_month_total(cash_price) / Decimal("3"), 2)

    def calculated_3_month_daily(self, cash_price=None):
        return round(self.calculated_3_month_total(cash_price) / Decimal("90"), 2)

    @property
    def deposit_amount(self):
        return self.calculated_deposit(self.default_cash_price or self.cash_price)

    @property
    def monthly_payment(self):
        return self.calculated_monthly_payment(self.default_cash_price or self.cash_price)

    @property
    def daily_payment(self):
        return self.calculated_daily_payment(self.default_cash_price or self.cash_price)

    @property
    def early_3_month_price(self):
        return self.calculated_3_month_total(self.default_cash_price or self.cash_price)

    @property
    def early_6_month_price(self):
        return self.calculated_6_month_total(self.default_cash_price or self.cash_price)

    def clean(self):
        super().clean()
        errors = {}

        if self.deposit_percent is not None:
            if self.deposit_percent < Decimal("13"):
                errors["deposit_percent"] = "Deposit percent cannot be below 13%."
            elif self.deposit_percent > Decimal("16"):
                errors["deposit_percent"] = "Deposit percent cannot be above 16%."

        if (
            self.min_cash_price is not None
            and self.default_cash_price is not None
            and self.max_cash_price is not None
            and not self.min_cash_price <= self.default_cash_price <= self.max_cash_price
        ):
            errors["default_cash_price"] = "Default cash price must be between min and max cash price."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.brand.name} {self.model_name} {self.specs}"
