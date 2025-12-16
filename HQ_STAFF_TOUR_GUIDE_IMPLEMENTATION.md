# HQ Staff Tour Guide PDF Implementation Summary

## Overview
Implemented a complete HQ Staff Tour Guide feature with downloadable PDF functionality. This replaces placeholder "PDF coming soon" text with a working document for HQ administrators.

## What Was Implemented

### 1. Dependencies
- **Added**: `reportlab==4.2.5` to `requirements.txt`
- Used for robust, cross-platform PDF generation (no system dependencies like WeasyPrint)

### 2. HTML Template
**File**: `templates/hq/staff_tour_guide.html`
- Clean, professional layout using existing HQ theme (glass-card design)
- Displays guide contents overview
- Working "Download PDF" button
- Links back to HQ dashboard
- Mobile-responsive

### 3. Views
**File**: `hq/views_contracts.py`

#### `staff_tour_guide(request)`
- Displays the tour guide HTML page
- Protected with `@hq_admin_required` decorator
- Returns rendered template

#### `staff_tour_guide_pdf(request)`
- Generates PDF on-the-fly using ReportLab
- Protected with `@hq_admin_required` decorator
- Returns PDF with correct headers:
  - `Content-Type: application/pdf`
  - `Content-Disposition: attachment; filename="hq_staff_tour_guide.pdf"`
- Never crashes (500-proof):
  - Checks if ReportLab is available (returns 503 if not)
  - Wraps all operations in try/except
  - Returns friendly error message on failure
- Logs download action to audit trail (if available)

**PDF Contents**:
1. Introduction & Purpose
2. HQ Dashboard Overview
3. Business Directory & Management
4. Subscription Management (trials, plans, activation)
5. Invoice & Payment Tracking
6. Account Support Tools
7. Analytics & Reporting
8. Contract Management
9. Common Troubleshooting
10. Security & Best Practices

### 4. URL Routing
**File**: `hq/urls.py`
- `hq:staff_tour_guide` → `/hq/staff/tour-guide/` (HTML page)
- `hq:staff_tour_guide_pdf` → `/hq/staff/tour-guide.pdf` (PDF download)
- Both routes conditionally added if `views_contracts` is available

### 5. Tests
**File**: `tests/test_hq_staff_tour_guide_pdf.py`

Comprehensive test coverage includes:

#### Permission Tests
- ✅ HQ users can access HTML page (200)
- ✅ HQ users can download PDF (200)
- ✅ Non-HQ users are blocked (403/302)
- ✅ Anonymous users redirected to login (302)

#### PDF Quality Tests
- ✅ Content-Type is `application/pdf`
- ✅ Content-Disposition header is correct
- ✅ Response starts with `%PDF` magic bytes
- ✅ PDF has substantial content (>1KB)

#### Robustness Tests
- ✅ Never returns 500 error
- ✅ Gracefully handles missing ReportLab (503)
- ✅ Multiple downloads work correctly
- ✅ URL patterns are registered correctly

#### Security Tests
- ✅ Staff-only users follow hq_admin_required rules
- ✅ Non-HQ users never receive PDF content
- ✅ HTML page includes download link

## How to Use

### As HQ Admin
1. Navigate to `/hq/staff/tour-guide/`
2. Click "Download PDF" button
3. PDF downloads as `hq_staff_tour_guide.pdf`
4. Open in any PDF viewer

### For Testing
```bash
# Run all tour guide tests
pytest tests/test_hq_staff_tour_guide_pdf.py -v

# Run specific test class
pytest tests/test_hq_staff_tour_guide_pdf.py::TestHQStaffTourGuidePDF -v
```

## Security & Permissions
- **HQ-Only**: Both HTML page and PDF download require `@hq_admin_required`
- **Non-HQ**: Redirected or blocked (403), never crash (500)
- **Anonymous**: Redirected to login
- **Audit Trail**: Downloads are logged if audit system is available

## Error Handling
All error cases handled gracefully:
- ❌ ReportLab not installed → Returns 503 with friendly message
- ❌ PDF generation fails → Returns 500 with error message (not crash)
- ❌ Non-HQ access → Returns 403/302 (blocked)
- ❌ Anonymous access → Returns 302 (login redirect)

## Definition of Done ✅
- [x] Tour guide HTML page created and styled
- [x] "Download PDF" button works
- [x] PDF generates successfully with ReportLab
- [x] PDF has correct Content-Type and Content-Disposition headers
- [x] PDF content is comprehensive and useful
- [x] HQ-only access enforced via decorators
- [x] Non-HQ users blocked (403/redirect)
- [x] Anonymous users redirected to login
- [x] Tests created for all scenarios
- [x] Tests verify no 500 errors
- [x] Tests verify PDF magic bytes
- [x] No linter errors
- [x] ReportLab added to requirements.txt

## Files Modified/Created

### Modified
- `requirements.txt` - Added reportlab
- `hq/views_contracts.py` - Added tour guide views
- `hq/urls.py` - Added tour guide URL routes

### Created
- `templates/hq/staff_tour_guide.html` - Tour guide HTML page
- `tests/test_hq_staff_tour_guide_pdf.py` - Comprehensive test suite
- `HQ_STAFF_TOUR_GUIDE_IMPLEMENTATION.md` - This document

## Future Enhancements (Optional)
- Add "last updated" timestamp to PDF
- Make PDF content configurable via admin
- Add images/diagrams to PDF
- Support multiple languages
- Add version history tracking
- Link from HQ dashboard sidebar

## Notes
- PDF is generated on-the-fly (not stored on disk)
- ReportLab chosen over WeasyPrint for:
  - No system dependencies (fonts, libraries)
  - More reliable on Windows/Render
  - Smaller installation footprint
  - Better programmatic control
- Content can be easily updated by editing the view function

