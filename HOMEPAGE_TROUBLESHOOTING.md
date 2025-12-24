# Homepage Not Showing Changes - Troubleshooting Guide

## ✅ Quick Fix: Access the Correct URL

Your homepage with the new growth metrics is at:

```
http://localhost:8000/landing/
```

**NOT** at `http://localhost:8000/` (that redirects to the dashboard for logged-in users)

## 🔄 If Changes Still Don't Show

### 1. Restart Django Development Server

```bash
# Stop the server (Ctrl+C in the terminal where it's running)
# Then restart:
python manage.py runserver
```

### 2. Clear Browser Cache

**Method A: Hard Refresh**
- **Windows/Linux:** `Ctrl + F5` or `Ctrl + Shift + R`
- **Mac:** `Cmd + Shift + R`

**Method B: Incognito/Private Window**
- Open a new incognito/private browsing window
- Navigate to `http://localhost:8000/landing/`

**Method C: Clear Cache Manually**
- **Chrome:** Settings → Privacy → Clear browsing data → Cached images and files
- **Firefox:** Settings → Privacy → Clear History → Cache
- **Edge:** Settings → Privacy → Clear browsing data → Cached images and files

### 3. Clear Django Template Cache (if enabled)

```bash
python manage.py shell
```

Then in the shell:
```python
from django.core.cache import cache
cache.clear()
exit()
```

### 4. Verify Template is Loading

Add this to your Django server output to confirm the template is being used:

Check the terminal where your Django server is running - you should see:
```
GET /landing/ HTTP/1.1" 200
```

## 🧪 Test the API Endpoint

Test the growth metrics API directly:

```bash
curl http://localhost:8000/landing/api/stats/
```

Expected response:
```json
{
    "total_merchants": 5,
    "total_agents": 12,
    "status": "success"
}
```

## 📱 What You Should See

When you visit `http://localhost:8000/landing/`, you should see:

1. **Hero Section** with the Emajinet branding
2. **NEW: Growth Metrics Box** below the subtitle:
   - Large animated numbers for "Active Merchants"
   - Large animated numbers for "Registered Agents"
   - Pulsing green dot with "Live platform metrics" text
3. **Reality → Solution Stats Section** (existing)
4. Other sections below

### Visual Example:

```
┌─────────────────────────────────────────┐
│  Doing business shouldn't be a headache │
│                                          │
│  ╔════════════════════════════════════╗ │
│  ║        5         │       12        ║ │ ← NEW!
│  ║  Active Merchants│Registered Agents║ │
│  ║    ● Live platform metrics          ║ │
│  ╚════════════════════════════════════╝ │
└─────────────────────────────────────────┘
```

## 🔍 Check for JavaScript Errors

Open browser DevTools (F12) and check the Console tab:
- You should see no errors
- Numbers should animate from 0 to the actual count

## 📂 Verify Files Were Saved

Check these files have the changes:

```bash
# Check if the metrics display is in the template
grep -n "platform-growth-metrics" staticpages/templates/staticpages/home.html

# Check if the API endpoint exists
grep -n "platform_stats_api" staticpages/views.py

# Check if the URL is registered
grep -n "platform_stats_api" staticpages/urls.py
```

## 🆘 Still Not Working?

### Check Django Settings

Ensure `staticpages` is in `INSTALLED_APPS`:

```python
# In your settings.py
INSTALLED_APPS = [
    # ...
    'staticpages',
    # ...
]
```

### Check URL Configuration

Verify in `cc/urls.py` (around line 412):

```python
path("landing/", include("staticpages.urls", "staticpages")),
```

### Enable Django Debug Mode

In your settings.py, temporarily enable:
```python
DEBUG = True
```

This will show detailed error messages if something is wrong.

## ✨ Expected Behavior

### On Page Load:
1. Metrics numbers animate from 0 to actual count (2 seconds)
2. Green dot pulses
3. Numbers are large and prominent

### Every 60 Seconds:
1. AJAX call to `/landing/api/stats/`
2. If numbers changed, they animate to new values
3. No page reload required

### On Mobile:
1. Metrics stack vertically
2. Smaller font sizes
3. Still fully functional

## 🎯 Quick Test Script

Create a file `test_homepage.py`:

```python
#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.test import Client

client = Client()
response = client.get('/landing/')

print(f"Status Code: {response.status_code}")
print(f"Template Used: {response.template_name if hasattr(response, 'template_name') else 'N/A'}")

if response.status_code == 200:
    content = response.content.decode('utf-8')
    
    if 'platform-growth-metrics' in content:
        print("✅ Growth metrics HTML found in response")
    else:
        print("❌ Growth metrics HTML NOT found in response")
    
    if 'totalMerchants' in content:
        print("✅ JavaScript variables found")
    else:
        print("❌ JavaScript variables NOT found")
    
    if 'Active Merchants' in content:
        print("✅ Metrics labels found")
    else:
        print("❌ Metrics labels NOT found")
else:
    print(f"❌ Page returned status {response.status_code}")
```

Run it:
```bash
python test_homepage.py
```

## 📞 Need More Help?

If none of these work:

1. Check if you're on the right branch
2. Verify all files were saved
3. Check Django logs for errors
4. Try accessing from a different browser
5. Restart your computer (clears all caches)

---

**Remember:** The homepage is at `/landing/` not `/`!

