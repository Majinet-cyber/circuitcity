# Pharmacy & Cosmetics Quick Start Guide

## 🚀 Using the Enhanced Pharmacy Dashboard

### Option 1: Wire the Enhanced View (Recommended)

**File**: `inventory/urls_pharmacy.py`

```python
from . import views_pharmacy_enhanced

urlpatterns = [
    # Use the enhanced dashboard
    path("", views_pharmacy_enhanced.pharmacy_dashboard_enhanced, name="dashboard"),
    
    # ... rest of your pharmacy URLs
]
```

### Option 2: Merge Into Existing View

Copy the logic from `inventory/views_pharmacy_enhanced.py` → `pharmacy_dashboard()` function into your existing `inventory/views_pharmacy.py`.

---

## 📋 Cosmetics Categories Available

Import from `inventory.pharmacy_constants`:

```python
from inventory.pharmacy_constants import PharmacyCategory

# Available categories:
PharmacyCategory.MEDICINE        # 💊 Medicine
PharmacyCategory.SKIN_CARE       # 🧴 Skin Care
PharmacyCategory.BODY_CARE       # 🧼 Body Care
PharmacyCategory.HAIR_CARE       # 💇 Hair Care
PharmacyCategory.PERFUME         # 🌸 Perfume
PharmacyCategory.PERSONAL_CARE   # 🧽 Personal Care
PharmacyCategory.OTHER           # 📦 Other
```

---

## 🏷️ Premium Brands Supported

### Skin Care
Nivea, Garnier, Dove, CeraVe, Olay, Vaseline, Neutrogena, L'Oréal

### Body Care
Dove, Nivea, Vaseline, Palmolive, Johnson & Johnson, Imperial Leather

### Hair Care
Pantene, Head & Shoulders, Garnier, L'Oréal, Tresemmé, Sunsilk

### Perfumes
Pure Black, Chris Adams, Lattafa, Rasasi, Ard Al Zaafaran, Arabic Collection

**Access brands**:
```python
from inventory.pharmacy_constants import COSMETICS_BRANDS, get_brands_for_category

# Get brands for a category
skin_care_brands = get_brands_for_category("skin_care")

# Get all brands
all_brands = get_all_brands()
```

---

## 🏆 Gamification Badges

4 data-driven badges automatically calculated:

1. **✨ Fresh Stock Hero** - No near-expiry batches
2. **💄 Cosmetics Champion** - 25%+ cosmetics revenue
3. **🛡️ Batch Guardian** - All batches have 30+ days to expiry
4. **📦 Stock Master** - 20+ active batches in inventory

**Calculate badges**:
```python
from inventory.pharmacy_constants import calculate_pharmacy_badges

pharmacy_data = {
    "near_expiry_count": 0,
    "cosmetics_revenue_pct": 30,
    "batches_count": 25,
    "all_batches_fresh": True,
}

badges = calculate_pharmacy_badges(pharmacy_data)
# Returns list of badge dicts with: name, icon, description, earned
```

---

## 📊 Dashboard Metrics

The enhanced dashboard calculates:

### Current Stock Metrics (not time-filtered):
- Total active batches
- Total stock value (at selling price)
- Total products count
- Near-expiry count (≤30 days)
- Expired batches count
- Low stock batches count

### Period Metrics (filtered by date range):
- Revenue (total sales)
- COGS (Cost of Goods Sold)
- Admin Wallet costs (from wallet transactions)
- Total costs (COGS + Admin)
- Profit (Revenue - Total Costs)
- Sales count

### Cosmetics Metrics:
- Cosmetics revenue
- Cosmetics revenue % of total
- Cosmetics products count
- Top cosmetics brands by revenue

---

## 🔧 Creating Cosmetics Products

```python
from inventory.models import MerchProduct
from inventory.pharmacy_constants import PharmacyCategory

# Create a cosmetics product
product = MerchProduct.objects.create(
    business=business,
    name="Nivea Body Lotion 400ml",
    kind="pharmacy",
    category=PharmacyCategory.SKIN_CARE,
    is_active=True
)

# Create a perfume
perfume = MerchProduct.objects.create(
    business=business,
    name="Pure Black Cologne 100ml",
    kind="pharmacy",
    category=PharmacyCategory.PERFUME,
    is_active=True
)
```

---

## 🧪 Testing

Run the pharmacy vertical tests:

```bash
python manage.py test inventory.tests.test_pharmacy_vertical
```

All 8 tests cover:
- Batch creation and management
- Expiry detection
- Low stock detection
- Cosmetics categorization
- Gamification badge logic
- Batches page rendering

---

## 🎨 Dashboard Features

### Period Selector
- Today
- Last 7 Days
- This Month
- Custom (with date picker)

### KPI Cards (6 cards)
1. Total Batches
2. Stock Value
3. Revenue (period-filtered)
4. Profit (period-filtered)
5. Costs (period-filtered)
6. Products Count

### Cosmetics Highlights
- Revenue & percentage breakdown
- Top brands ranking
- Products count

### Alerts
- Near-expiry warnings
- Expired batches alerts
- Low stock notifications
- "All systems go" when no alerts

### Quick Actions
- + Add Medicine
- + Add Cosmetic
- View All Batches
- Record Sale

---

## 💡 Tips

1. **Brand Recognition**: The system extracts brands from product names automatically. Include brand names in your product names for better tracking (e.g., "Nivea Body Lotion" not just "Body Lotion").

2. **Categories**: Always set the `category` field when creating pharmacy products to enable proper filtering and cosmetics tracking.

3. **Admin Wallet Integration**: The dashboard automatically pulls admin costs from the wallet app if available. No additional setup needed.

4. **Gamification**: Badges update in real-time based on actual data. No manual badge management required.

---

## 📱 Mobile-Friendly

The dashboard is fully responsive with:
- Stacked layout on mobile
- Touch-friendly buttons
- Optimized card sizes
- Horizontal scrolling for tables when needed

---

**Ready to go! 🚀**

