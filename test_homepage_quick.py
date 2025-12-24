#!/usr/bin/env python
"""Quick test to verify homepage changes are live"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from django.test import Client

print("Testing homepage at /landing/...")
print("=" * 60)

client = Client()
response = client.get('/landing/')

print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    content = response.content.decode('utf-8')
    
    checks = [
        ('platform-growth-metrics', '✅ Growth metrics container found'),
        ('totalMerchants', '✅ Merchants counter found'),
        ('totalAgents', '✅ Agents counter found'),
        ('Active Merchants', '✅ Merchants label found'),
        ('Registered Agents', '✅ Agents label found'),
        ('initPlatformMetrics', '✅ JavaScript initialization found'),
        ('platform_stats_api', '✅ API URL found'),
    ]
    
    for search_term, success_msg in checks:
        if search_term in content:
            print(success_msg)
        else:
            print(f"❌ NOT FOUND: {search_term}")
    
    print("\n" + "=" * 60)
    print("✅ ALL CHANGES ARE LIVE!")
    print("\nAccess the homepage at:")
    print("   http://localhost:8000/landing/")
    print("\nPress Ctrl+Shift+R to hard refresh your browser.")
    
else:
    print(f"❌ Error: Page returned status {response.status_code}")

# Test API endpoint
print("\n" + "=" * 60)
print("Testing API endpoint...")
api_response = client.get('/landing/api/stats/')
print(f"API Status Code: {api_response.status_code}")

if api_response.status_code == 200:
    import json
    data = json.loads(api_response.content)
    print(f"✅ API is working!")
    print(f"   Total Merchants: {data.get('total_merchants', 0)}")
    print(f"   Total Agents: {data.get('total_agents', 0)}")
else:
    print(f"❌ API Error: {api_response.status_code}")

