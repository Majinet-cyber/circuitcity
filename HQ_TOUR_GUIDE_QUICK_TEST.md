# Quick Test Guide: HQ Staff Tour Guide PDF

## Prerequisites
```bash
# Install reportlab
pip install reportlab==4.2.5
# or
pip install -r requirements.txt
```

## Manual Testing Steps

### 1. As HQ Admin (Should Work)
```
1. Log in as superuser/HQ admin
2. Navigate to: http://localhost:8000/hq/staff/tour-guide/
3. Verify: Page loads with "HQ Staff Tour Guide" heading
4. Click "Download PDF" button
5. Verify: PDF downloads as "hq_staff_tour_guide.pdf"
6. Open PDF and verify:
   ✓ Opens successfully
   ✓ Contains "Emajinet / Circuit City" title
   ✓ Has multiple sections (Dashboard, Subscriptions, etc.)
   ✓ Is readable and properly formatted
```

### 2. As Non-HQ User (Should Block)
```
1. Log in as regular manager/agent
2. Try to access: http://localhost:8000/hq/staff/tour-guide/
3. Verify: Redirected or see 403 Forbidden (NOT 500 error)
4. Try direct PDF: http://localhost:8000/hq/staff/tour-guide.pdf
5. Verify: Blocked (NOT 500, NOT downloading PDF)
```

### 3. As Anonymous User (Should Redirect)
```
1. Log out completely
2. Try to access: http://localhost:8000/hq/staff/tour-guide/
3. Verify: Redirected to login page
4. Try direct PDF: http://localhost:8000/hq/staff/tour-guide.pdf
5. Verify: Redirected to login (NOT downloading PDF)
```

## Automated Testing
```bash
# Run all tour guide tests
pytest tests/test_hq_staff_tour_guide_pdf.py -v

# Expected output: All tests pass ✓

# Run with coverage
pytest tests/test_hq_staff_tour_guide_pdf.py --cov=hq.views_contracts -v
```

## Test Checklist
- [ ] HQ user can view HTML page (200)
- [ ] HQ user can download PDF (200)
- [ ] PDF has correct Content-Type (application/pdf)
- [ ] PDF has correct Content-Disposition header
- [ ] PDF starts with %PDF bytes
- [ ] PDF is substantial (>1KB)
- [ ] Non-HQ user blocked from HTML (403/302)
- [ ] Non-HQ user blocked from PDF (403/302)
- [ ] Anonymous user redirected to login (302)
- [ ] No 500 errors in any scenario
- [ ] Tests pass

## Troubleshooting

### "reportlab not found" error
```bash
pip install reportlab==4.2.5
```

### PDF shows 503 error
- ReportLab not installed in your environment
- Install with: `pip install reportlab`

### URL not found (404)
- Verify `views_contracts` is imported in `hq/urls.py`
- Check that conditional block adds tour guide routes
- Run: `python manage.py show_urls | grep tour-guide`

### Tests fail with import errors
```bash
# Ensure pytest is installed
pip install pytest pytest-django

# Set DJANGO_SETTINGS_MODULE
export DJANGO_SETTINGS_MODULE=cc.settings
# or on Windows:
set DJANGO_SETTINGS_MODULE=cc.settings
```

## Success Criteria ✅
All of the following should be true:
1. HQ admin can access HTML page
2. HQ admin can download working PDF
3. PDF opens in viewer (Adobe, Chrome, etc.)
4. PDF contains tour guide content
5. Non-HQ users are blocked (not 500)
6. Anonymous users redirected to login
7. All tests pass
8. No linter errors

## Quick Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/test_hq_staff_tour_guide_pdf.py -v

# Start dev server
python manage.py runserver

# Test URLs
curl -I http://localhost:8000/hq/staff/tour-guide/
# Should return 302 (redirect to login) if not logged in
```

## URLs Created
- HTML: `/hq/staff/tour-guide/`
- PDF: `/hq/staff/tour-guide.pdf`
- URL names: `hq:staff_tour_guide`, `hq:staff_tour_guide_pdf`

