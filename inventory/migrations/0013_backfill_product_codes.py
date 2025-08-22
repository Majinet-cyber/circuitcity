from django.db import migrations
from django.utils.text import slugify

def populate_codes(apps, schema_editor):
    Product = apps.get_model("inventory", "Product")

    # Cache existing codes to avoid extra queries in the collision loop
    existing = set(
        Product.objects.exclude(code__isnull=True).exclude(code__exact="").values_list("code", flat=True)
    )

    for p in Product.objects.all():
        if p.code:
            existing.add(p.code)
            continue

        # Build a base string from brand/model/variant; fallback to pk if too bare
        base_txt = " ".join(filter(None, [p.brand, p.model, p.variant])).strip()
        base = slugify(base_txt) if base_txt else f"p{p.pk}"
        if not base:
            base = f"p{p.pk}"

        # Ensure uniqueness; clip to 64 chars
        candidate = base[:64]
        i = 1
        while candidate in existing:
            suffix = f"-{i}"
            candidate = (base[: (64 - len(suffix))] + suffix) if len(base) + len(suffix) > 64 else base + suffix
            i += 1

        p.code = candidate
        p.save(update_fields=["code"])
        existing.add(candidate)

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0012_product_code_product_cost_price_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_codes, reverse_code=noop),
    ]
