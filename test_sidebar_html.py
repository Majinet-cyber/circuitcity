#!/usr/bin/env python
"""
Test if accessories items appear in the rendered HTML.
Run Django test client to fetch the scan-in page and check the HTML.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership
from inventory.models import Location

User = get_user_model()

print("=" * 80)
print("TESTING ACCESSORIES IN SIDEBAR HTML")
print("=" * 80)

# Create test user and business
try:
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        print("❌ No superuser found. Creating one...")
        user = User.objects.create_superuser('test_admin', 'admin@test.com', 'password')
    
    business = Business.objects.filter(business_kind='phones').first()
    if not business:
        print("❌ No phones business found. Creating one...")
        business = Business.objects.create(
            name='Test Phones Business',
            code='TEST',
            business_kind='phones'
        )
        location = Location.objects.create(
            business=business,
            name='Main Store'
        )
    
    # Ensure membership exists
    membership, created = Membership.objects.get_or_create(
        user=user,
        business=business,
        defaults={'role': 'MANAGER', 'status': 'ACTIVE'}
    )
    
    print(f"✓ User: {user.username}")
    print(f"✓ Business: {business.name} ({business.business_kind})")
    print()
    
    # Create test client and login
    client = Client()
    client.force_login(user)
    
    # Set business in session
    session = client.session
    session['active_business_id'] = business.id
    session.save()
    
    print("Fetching /inventory/scan-in/ ...")
    response = client.get('/inventory/scan-in/')
    
    print(f"Status code: {response.status_code}")
    print()
    
    if response.status_code != 200:
        print(f"❌ ERROR: Got {response.status_code} status code")
        sys.exit(1)
    
    html = response.content.decode('utf-8')
    
    # Search for accessories
    print("=" * 80)
    print("SEARCH RESULTS:")
    print("=" * 80)
    
    search_terms = [
        'Accessories',
        'Stock In Accessories',
        'nav-phones-accessories',
        'phones_accessories_dashboard',
        'phones_accessories_stock_in',
    ]
    
    for term in search_terms:
        count = html.count(term)
        status = "✓" if count > 0 else "✗"
        print(f"{status} '{term}': found {count} times")
    
    print()
    print("=" * 80)
    print("DEBUG COMMENTS FROM TEMPLATE:")
    print("=" * 80)
    
    # Extract DEBUG comments
    import re
    debug_comments = re.findall(r'<!-- DEBUG: (.*?) -->', html)
    for comment in debug_comments:
        print(f"  {comment}")
    
    print()
    
    # Check sidebar_items in context
    if hasattr(response, 'context') and response.context:
        sidebar_items = response.context.get('sidebar_items', [])
        print("=" * 80)
        print(f"SIDEBAR_ITEMS IN CONTEXT: {len(sidebar_items)} items")
        print("=" * 80)
        
        main_items = [item for item in sidebar_items if item.get('section') == 'MAIN']
        print(f"\nMAIN section items ({len(main_items)}):")
        for item in main_items:
            print(f"  - {item.get('label')} (key: {item.get('key')}, testid: {item.get('testid', 'MISSING')})")
        
        acc_items = [item for item in sidebar_items if 'accessories' in item.get('key', '')]
        print(f"\nAccessories items ({len(acc_items)}):")
        for item in acc_items:
            print(f"  - {item.get('label')}")
            print(f"    key: {item.get('key')}")
            print(f"    url: {item.get('url')}")
            print(f"    section: {item.get('section')}")
            print(f"    testid: {item.get('testid', 'MISSING')}")
    
    print()
    
    # Final verdict
    accessories_count = html.count('Accessories')
    if accessories_count > 0:
        print("✅ SUCCESS: 'Accessories' found in HTML!")
        print(f"   Appears {accessories_count} times in the page")
    else:
        print("❌ FAILURE: 'Accessories' NOT found in HTML")
        print()
        print("Possible causes:")
        print("1. sidebar_items not being passed to template")
        print("2. URL resolution failing")
        print("3. Items being filtered out by template logic")
        print("4. Template not being used (wrong base template?)")
        sys.exit(1)

except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

