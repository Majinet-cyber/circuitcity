content = open('staticpages/templates/staticpages/home.html', encoding='utf-8').read()
lines = content.split('\n')
print(f'Total lines: {len(lines)}')
print()
print('All <section tags:')
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if stripped.startswith('<section '):
        print(f'  L{i}: {stripped[:120]}')

print()
print('Key content checks:')
checks = [
    'Get Started Free', 'See How It Works', 'Start Free Trial',
    'how-it-works', 'How It Works',
    'renewable-energy', 'System Sizing Engine', 'Flagship Vertical',
    'business-simulator', 'liveMetricsContainer', 'liveMetricsNote', 'lm-skeleton',
    'pricing-snapshot', 'pricing-grid',
    'reality-stats', 'FinScope', 'smart-recommendations', 'restock',
    'mobileMenu', 'Features', 'Sign In',
    'Built in Malawi, for Africa', 'Faith Banda',
    'revenue', 'profit',
    'CURRENT_YEAR',
]
for c in checks:
    print(f'  {c}: {c in content}')
