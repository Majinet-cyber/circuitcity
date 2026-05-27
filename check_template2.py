content = open('staticpages/templates/staticpages/home.html', encoding='utf-8').read()
lines = content.split('\n')
# Find all section IDs
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if '<section ' in stripped or 'SECTION' in stripped and '==' in stripped:
        print(f'  Line {i}: {stripped[:120]}')
