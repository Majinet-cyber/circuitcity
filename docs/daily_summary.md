# Daily Summary Emails

Automated per-business daily summary emails that are **vertical-aware**: the content
sent to a Retail/Shop business is completely different from what a Gym or Car-Hire
business receives.

---

## Architecture Overview

```
Celery Beat (hourly)
    └── notifications.tasks_daily_summary.send_daily_summaries
            └── for each enabled DailySummarySettings:
                    ├── timezone + hour gate (skips if wrong hour)
                    ├── idempotency gate (skips if last_sent_date == today)
                    ├── recipients gate (skips if no active recipients)
                    ├── get_provider(business)  ← registry dispatch
                    │       ├── GymDailySummaryProvider
                    │       ├── CarHireDailySummaryProvider
                    │       └── RetailDailySummaryProvider  (default)
                    ├── provider.get_metrics(business, report_date)
                    ├── provider.render_email(business, metrics, report_date)
                    └── EmailMultiAlternatives.send()
```

---

## Step 1 — Set the Business Vertical

Every Business has a `business_kind` field (in `tenants/models.py`).  This field
drives which provider is selected.

**Via Django Admin:**

1. Go to **Admin → Tenants → Businesses**.
2. Open the business record.
3. Set **Business kind** to one of:

| Value | Vertical | Provider |
|---|---|---|
| `phones` | Phones & Electronics | Retail |
| `grocery` | Grocery / General | Retail |
| `pharmacy` | Cosmetics & Pharmacy | Retail |
| `clothing` | Clothing | Retail |
| `liquor` | Liquor / Bar | Retail |
| `hardware` | Hardware & General Dealers | Retail |
| `cement` | Cement / Building Materials | Retail |
| `farm` | Farm Manager | Retail |
| `welding` | Welding Workshop | Retail |
| `gym` | Gym / Fitness | **Gym** |
| `car_hire` | Car Hire Service | **Car Hire** |

4. Save.

**Programmatically:**

```python
from tenants.models import Business

business = Business.objects.get(slug="my-shop")
business.business_kind = "grocery"
business.save(update_fields=["business_kind"])
```

---

## Step 2 — Configure Per-Business Settings

### Via the Manager UI

Visit `/notifications/daily-summary/settings/` while logged in as a Manager
for the target business.  The page lets you:

- **Enable/disable** the daily summary.
- Set the **send hour** (0–23 in the selected timezone).
- Choose the **timezone** (default: `Africa/Blantyre`).
- **Add / remove recipients**.

### Via Django Admin

Go to **Admin → Notifications → Daily Summary Settings**.

Each row corresponds to one business.  Use the inline to manage recipients from
the same screen.

### Programmatically

```python
from notifications.models import DailySummarySettings, BusinessEmailRecipient

# Get-or-create settings
ds = DailySummarySettings.for_business(business)
ds.is_enabled = True
ds.send_hour = 7            # 07:00 in the business timezone
ds.timezone = "Africa/Blantyre"
ds.save()

# Add a recipient
BusinessEmailRecipient.objects.get_or_create(
    business=business,
    email="owner@example.com",
    defaults={"name": "Jane Owner", "is_active": True},
)
```

---

## Step 3 — Add Recipients

Recipients are stored in `BusinessEmailRecipient`.  A business can have
multiple recipients; they **do not need a CircuitCity account**.

- Removing a recipient via the UI sets `is_active = False` (soft-delete).
  The email stops being sent but the row is preserved in history.
- To permanently delete, use Django Admin → Daily Summary Recipients.
- Duplicate emails for the same business are silently ignored (`unique_together`).

---

## Step 4 — Celery Beat Schedule

The master task runs **every hour at :00** (configured in `cc/settings.py`):

```python
"daily-summary-emails": {
    "task": "notifications.tasks_daily_summary.send_daily_summaries",
    "schedule": crontab(minute=0),
},
```

Each business self-gates: the task checks `now_local.hour == ds.send_hour` before
sending.  This means a business configured to send at `07:00 Africa/Blantyre`
will only receive its email during the 07:00 UTC+2 cycle.

**To start Celery Beat locally:**

```bash
# Worker
celery -A cc worker -l info

# Beat scheduler (separate process)
celery -A cc beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
# — OR, if using the static schedule in settings.py —
celery -A cc beat -l info
```

---

## Safeguards

| Guard | Mechanism |
|---|---|
| No recipients | Skipped; logged at INFO |
| Already sent today | `DailySummarySettings.last_sent_date == today`; skipped |
| Wrong hour | `now_local.hour != ds.send_hour`; skipped |
| Provider error | Each metric sub-query is wrapped in try/except; returns safe 0 defaults |
| Disabled | `DailySummarySettings.is_enabled = False`; excluded from queryset |

---

## Testing Manually

**Trigger the task immediately** (useful during development):

```bash
celery -A cc call notifications.tasks_daily_summary.send_daily_summaries
```

**Force send for one business** (bypasses hour + date gate) — open a Django shell:

```python
from notifications.daily_summary import get_provider
from datetime import date

business = Business.objects.get(slug="my-shop")
provider = get_provider(business)
metrics = provider.get_metrics(business, date.today())
print(metrics)
html, text = provider.render_email(business, metrics, date.today())
print(text)
```

**Run the test suite:**

```bash
python manage.py test notifications.tests.test_daily_summary --verbosity=2
```

The suite covers:

- Registry routing (gym / car-hire / retail / unknown kind)
- Retail provider: `total_cogs` and `top_product` keys present
- Gym provider: `total_cogs` and `top_product` keys **absent**
- Car-hire provider: `total_cogs` and `top_product` keys **absent**
- `render_email()` returns `(html, text)` tuple for all providers
- `DailySummarySettings.for_business()` idempotency
- Task safeguards: no recipients, already sent today, wrong hour
- Full send cycle: last_sent_date updated on success

---

## Email Format

| Field | Value |
|---|---|
| Subject | `[{BusinessName}] Daily Summary — YYYY-MM-DD` |
| From | `DEFAULT_FROM_EMAIL` from settings |
| To | All active `BusinessEmailRecipient` addresses for the business |
| Multipart | HTML + plain text |

Templates live in `templates/emails/daily_summary/`:

```
retail.html / retail.txt    — Sales, COGS, Profit, Top Product, Low Stock
gym.html    / gym.txt       — Members, Revenue, Check-ins, Renewals
car_hire.html / car_hire.txt — Fleet, Revenue, Utilisation, Overdue
```

---

## Adding a New Vertical

1. Add the new `BusinessKind` choice to `inventory/business_kinds.py`.
2. Create `notifications/daily_summary/<vertical>.py` implementing
   `DailySummaryProvider` (see `base.py` for the interface).
3. Register it in `notifications/daily_summary/registry.py`.
4. Create `templates/emails/daily_summary/<vertical>.html` and `.txt`.
5. Write tests in `notifications/tests/test_daily_summary.py`.

All existing businesses with unknown kinds automatically fall back to
`RetailDailySummaryProvider`.
