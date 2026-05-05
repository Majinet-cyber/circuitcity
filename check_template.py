content = open('staticpages/templates/staticpages/home.html', encoding='utf-8').read()
print('pricing-snapshot count:', content.count('pricing-snapshot'))
print('id=pricing-snapshot:', 'id="pricing-snapshot"' in content)
print('pricing sections with id=pricing:', content.count('id="pricing"'))
print('Total lines:', content.count('\n'))
for i, line in enumerate(content.split('\n'), 1):
    if 'id="pricing' in line:
        print(f'  Line {i}: {line.strip()[:100]}')
