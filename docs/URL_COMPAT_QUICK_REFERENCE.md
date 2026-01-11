# URL Compatibility Quick Reference

## ✅ Available URL Names (No Namespace Required)

All of these can be used with `reverse('name')` without any namespace prefix:

| URL Name | Resolves To | Example Usage |
|----------|-------------|---------------|
| `home` | `/home/` | `reverse('home')` or `{% url 'home' %}` |
| `stock` | `inventory:stock_list` | `reverse('stock')` |
| `sell` | `inventory:scan_sold` | `reverse('sell')` |
| `scan` | `inventory:scan_in` | `reverse('scan')` |
| `wallet` | `wallet:agent_wallet` | `reverse('wallet')` |
| `sim` | `simulator:home` | `reverse('sim')` |
| `businesses` | `hq:business_directory` | `reverse('businesses')` |
| `pharmacy_stock_in` | `pharmacy:stock_in` | `reverse('pharmacy_stock_in')` |
| `member_qr_image` | `gym:member_qr_png` | `reverse('member_qr_image')` |
| `export_monthly_costs` | (stub - not implemented) | `reverse('export_monthly_costs')` |

## 📝 How It Works

1. All compatibility aliases are defined in **`cc/urls_compat.py`** (SSOT)
2. URLConf files import via: `from cc.urls_compat import get_compat_urlpatterns`
3. Patterns are added with: `urlpatterns += get_compat_urlpatterns()`

## 🔍 URLConf Files That Include Compat Patterns

- `cc/urls.py` (root)
- `inventory/urls.py`
- `core/urls_app_router.py`
- `hq/urls.py`
- `inventory/urls_router.py`

## 🧪 Testing

Run the compatibility tests:

```bash
python manage.py test tests.test_url_compat_ssot -v 2
```

All 23 tests should pass.

## 🚀 Adding New Compatibility Aliases

**Step 1:** Edit `cc/urls_compat.py` only

Add your pattern to the `get_compat_urlpatterns()` function:

```python
path("__alias__/my-name/", RedirectView.as_view(pattern_name="app:view", permanent=False), name="my_name"),
```

**Step 2:** Add test in `tests/test_url_compat_ssot.py`

```python
def test_reverse_my_name_works(self):
    """Test reverse('my_name') works without namespace."""
    try:
        url = reverse('my_name')
        self.assertIsNotNone(url)
        self.assertIn('__alias__/my-name/', url)
    except NoReverseMatch as e:
        self.fail(f"reverse('my_name') should work but raised NoReverseMatch: {e}")
```

**Step 3:** Run tests to verify

```bash
python manage.py test tests.test_url_compat_ssot::URLCompatSSotTest::test_reverse_my_name_works -v 2
```

## ⚠️ Important Rules

1. **NEVER** add compatibility aliases directly to URLConf files
2. **ALWAYS** add them to `cc/urls_compat.py` only
3. **ALWAYS** add a test for new aliases
4. Use `__alias__/` prefix to avoid conflicts with real routes
5. Prefer namespaced URLs in new code (e.g., `inventory:stock_list`)

## 🔗 Canonical Namespaced Routes (Preferred)

For new code, prefer using namespaced URLs:

```python
# ✅ Preferred (explicit namespace)
reverse('inventory:stock_list')

# ⚠️ Legacy (works but less clear)
reverse('stock')
```

Namespaced routes are more explicit and less likely to have naming conflicts.

