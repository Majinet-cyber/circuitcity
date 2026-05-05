content = open('staticpages/templates/staticpages/home.html', encoding='utf-8').read()
lines = content.split('\n')
# Find all section opening tags
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if stripped.startswith('<section '):
        print(f'  Line {i}: {stripped[:120]}')
print()
# Check specific elements
for item in ['how-it-works', 'renewable-energy', 'business-simulator', 'pricing-snapshot',
             'liveMetricsContainer', 'liveMetricsNote', 'lm-skeleton', 'Get Started Free',
             'FinScope', 'reality-stats', 'smart-recommendations', 'revenue', 'Team',
             'Built in Malawi, for Africa']:
    found = item in content
    print(f'{item}: {found}')
