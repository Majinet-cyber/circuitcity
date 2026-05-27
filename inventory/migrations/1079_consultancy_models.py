"""
Migration: Add Consultancy & Services vertical models
(ConsultancyClient, ConsultancyProject, ConsultancyQuote, ConsultancyQuoteItem,
 ConsultancyInvoice, ConsultancyInvoiceItem, ConsultancyPayment, ConsultancyExpense)
"""
from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1078_mixed_retail_models"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsultancyClient",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("company", models.CharField(blank=True, max_length=255)),
                ("email", models.EmailField(blank=True)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("address", models.TextField(blank=True)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="consultancy_clients",
                    to="tenants.business",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["name"], "verbose_name": "Client"},
        ),
        migrations.CreateModel(
            name="ConsultancyProject",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("project_type", models.CharField(
                    choices=[("project","Project"),("retainer","Retainer"),("service","One-off Service"),("repair","Repair"),("advisory","Advisory")],
                    default="project", max_length=20,
                )),
                ("status", models.CharField(
                    choices=[("lead","Lead"),("quoted","Quoted"),("approved","Approved"),("in_progress","In Progress"),("delivered","Delivered"),("paid","Paid"),("overdue","Overdue"),("cancelled","Cancelled")],
                    default="lead", max_length=20,
                )),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("deadline", models.DateField(blank=True, null=True)),
                ("agreed_value", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("monthly_retainer", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("notes", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="consultancy_projects",
                    to="tenants.business",
                )),
                ("client", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="projects",
                    to="inventory.consultancyclient",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_consultancy_projects",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "Project"},
        ),
        migrations.CreateModel(
            name="ConsultancyQuote",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("quote_number", models.CharField(blank=True, max_length=50)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("subtotal", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("discount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("tax", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("status", models.CharField(
                    choices=[("draft","Draft"),("sent","Sent"),("accepted","Accepted"),("rejected","Rejected"),("expired","Expired")],
                    default="draft", max_length=20,
                )),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="consultancy_quotes",
                    to="tenants.business",
                )),
                ("client", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="quotes",
                    to="inventory.consultancyclient",
                )),
                ("project", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="quotes",
                    to="inventory.consultancyproject",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_consultancy_quotes",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "Quote"},
        ),
        migrations.CreateModel(
            name="ConsultancyQuoteItem",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("description", models.CharField(max_length=255)),
                ("quantity", models.DecimalField(decimal_places=2, default=Decimal("1"), max_digits=10)),
                ("unit_price", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("total", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("quote", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="line_items",
                    to="inventory.consultancyquote",
                )),
            ],
            options={"ordering": ["sort_order", "pk"]},
        ),
        migrations.CreateModel(
            name="ConsultancyInvoice",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("invoice_number", models.CharField(blank=True, max_length=50)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("subtotal", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("discount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("tax", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("amount_paid", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("status", models.CharField(
                    choices=[("draft","Draft"),("sent","Sent"),("partial","Partially Paid"),("paid","Paid"),("overdue","Overdue")],
                    default="draft", max_length=20,
                )),
                ("due_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("is_void", models.BooleanField(default=False)),
                ("issued_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="consultancy_invoices",
                    to="tenants.business",
                )),
                ("client", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="invoices",
                    to="inventory.consultancyclient",
                )),
                ("project", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="invoices",
                    to="inventory.consultancyproject",
                )),
                ("quote", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="invoices",
                    to="inventory.consultancyquote",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_consultancy_invoices",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-issued_at"], "verbose_name": "Invoice"},
        ),
        migrations.CreateModel(
            name="ConsultancyInvoiceItem",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("description", models.CharField(max_length=255)),
                ("quantity", models.DecimalField(decimal_places=2, default=Decimal("1"), max_digits=10)),
                ("unit_price", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("total", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("invoice", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="line_items",
                    to="inventory.consultancyinvoice",
                )),
            ],
            options={"ordering": ["sort_order", "pk"]},
        ),
        migrations.CreateModel(
            name="ConsultancyPayment",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("payment_method", models.CharField(
                    choices=[("cash","Cash"),("bank","Bank Transfer"),("airtel_money","Airtel Money"),("tnm_mpamba","TNM Mpamba"),("cheque","Cheque"),("other","Other")],
                    default="cash", max_length=20,
                )),
                ("reference", models.CharField(blank=True, max_length=100)),
                ("notes", models.TextField(blank=True)),
                ("paid_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="consultancy_payments",
                    to="tenants.business",
                )),
                ("invoice", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="payments",
                    to="inventory.consultancyinvoice",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-paid_at"], "verbose_name": "Payment"},
        ),
        migrations.CreateModel(
            name="ConsultancyExpense",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ("category", models.CharField(
                    choices=[("salaries","Salaries"),("rent","Rent / Office"),("software","Software & Tools"),("transport","Transport"),("utilities","Utilities"),("marketing","Marketing"),("subcontract","Subcontracting"),("training","Training"),("other","Other")],
                    default="other", max_length=30,
                )),
                ("description", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("expense_date", models.DateField(default=django.utils.timezone.localdate)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="consultancy_expenses",
                    to="tenants.business",
                )),
                ("project", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="expenses",
                    to="inventory.consultancyproject",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-expense_date"], "verbose_name": "Expense"},
        ),
    ]
