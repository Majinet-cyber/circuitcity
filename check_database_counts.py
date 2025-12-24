#!/usr/bin/env python
"""Check database counts for businesses and agents"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc.settings')
django.setup()

from tenants.models import Business, Membership
from django.contrib.auth import get_user_model

User = get_user_model()

print("="*60)
print("DATABASE COUNTS CHECK")
print("="*60)

# Check Businesses
total_biz = Business.objects.count()
print(f"\n📊 BUSINESSES:")
print(f"   Total: {total_biz}")

if total_biz > 0:
    # Show sample businesses
    print(f"\n   Sample businesses:")
    for biz in Business.objects.all()[:5]:
        print(f"   - {biz.name}")

# Check Memberships
total_memberships = Membership.objects.count()
print(f"\n👥 MEMBERSHIPS:")
print(f"   Total: {total_memberships}")

if total_memberships > 0:
    # Count by role
    roles = Membership.objects.values_list('role', flat=True).distinct()
    for role in roles:
        count = Membership.objects.filter(role=role).count()
        print(f"   {role}: {count}")
    
    # Show sample memberships
    print(f"\n   Sample memberships:")
    for mem in Membership.objects.select_related('user', 'business').all()[:5]:
        print(f"   - {mem.user.username} @ {mem.business.name} ({mem.role})")

# Check Users
total_users = User.objects.count()
print(f"\n👤 USERS:")
print(f"   Total: {total_users}")

# What the API query would return
print("\n"+"="*60)
print("API QUERY RESULTS (what homepage shows):")
print("="*60)

merchants_count = Business.objects.count()
print(f"Total Merchants: {merchants_count}")

# Try different agent queries
agent_queries = [
    ("role__icontains='agent'", Membership.objects.filter(role__icontains='agent').count()),
    ("role__in=['AGENT', 'agent']", Membership.objects.filter(role__in=['AGENT', 'agent']).count()),
    ("role='AGENT'", Membership.objects.filter(role='AGENT').count()),
    ("role='agent'", Membership.objects.filter(role='agent').count()),
]

for query_desc, count in agent_queries:
    print(f"Agents ({query_desc}): {count}")

# Check if distinct('user') works
try:
    distinct_count = Membership.objects.filter(role__icontains='agent').values('user').distinct().count()
    print(f"Distinct agent users: {distinct_count}")
except Exception as e:
    print(f"Distinct query error: {e}")

print("\n"+"="*60)
print("RECOMMENDATION:")
print("="*60)

if total_biz == 0:
    print("⚠️  No businesses in database - need to seed data")

if total_memberships == 0:
    print("⚠️  No memberships in database - need to seed data")
else:
    agent_count = Membership.objects.filter(role__icontains='agent').count()
    if agent_count == 0:
        print("⚠️  No agent memberships found")
        print("    Check the exact role values in your database")

