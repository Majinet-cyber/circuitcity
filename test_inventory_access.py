"""Quick test to check inventory/list/ access"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.test import Client, RequestFactory
from django.contrib.auth import get_user_model
from tenants.models import Business, Membership

User = get_user_model()

# Create test client
client = Client()

# Try to get or create a test user
try:
    user = User.objects.first()
    if not user:
        print("❌ No users in database")
        exit(1)
    
    print(f"✓ Found user: {user.username}")
    
    # Login
    client.force_login(user)
    print(f"✓ Logged in as {user.username}")
    
    # Try to access inventory/list/
    print("\nAttempting to access /inventory/list/...")
    response = client.get('/inventory/list/', HTTP_HOST='localhost')
    
    print(f"\nResponse status: {response.status_code}")
    
    if response.status_code == 500:
        print("❌ SERVER ERROR (500)")
        # Print any error info
        if hasattr(response, 'content'):
            error_text = response.content.decode('utf-8')
            if 'Traceback' in error_text or 'Exception' in error_text:
                # Extract key parts
                lines = error_text.split('\n')
                for i, line in enumerate(lines):
                    if 'Exception' in line or 'Error' in line:
                        print(f"\n{'='*60}")
                        print("ERROR FOUND:")
                        print(f"{'='*60}")
                        # Print context around the error
                        start = max(0, i-5)
                        end = min(len(lines), i+10)
                        for j in range(start, end):
                            print(lines[j])
                        break
    elif response.status_code == 302:
        print(f"✓ Redirect to: {response.url}")
    elif response.status_code == 200:
        print("✓ SUCCESS - Page loaded")
    else:
        print(f"? Unexpected status: {response.status_code}")
        
except Exception as e:
    print(f"\n❌ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

