import django, os
os.environ['DJANGO_SETTINGS_MODULE'] = 'cc.settings'
django.setup()

from staticpages.views import get_all_verticals
vs = get_all_verticals()
print('Verticals:')
for v in vs[:10]:
    print('  ', v['name'])

from staticpages.pricing_config import PRICING_TIERS
print('Pricing tiers:')
for t in PRICING_TIERS:
    print('  ', t.get('name'), t.get('price_monthly'))
