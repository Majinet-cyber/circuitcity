# Data Deletion Policy - Quick Reference

## Overview
A Data Deletion Policy page has been implemented for Meta (WhatsApp/Facebook) app compliance and general data protection requirements.

## URL Information

### Development URL
```
http://localhost:8000/home/data-deletion/
```

### Production URL (for Meta)
```
https://<your-domain>/home/data-deletion/
```

**Note:** Replace `<your-domain>` with your actual production domain (e.g., `emajinet.africa` or `app.emajinet.africa`)

## Implementation Details

### Files Created/Modified

1. **View** - `staticpages/views.py`
   - Added `data_deletion()` view function

2. **URL Pattern** - `staticpages/urls.py`
   - Added route: `path('data-deletion/', views.data_deletion, name='data_deletion')`
   - Full URL path: `/home/data-deletion/`

3. **Template** - `staticpages/templates/staticpages/data_deletion.html`
   - New template matching the style of Privacy and Terms pages
   - Contains complete data deletion policy

4. **Home Page** - `staticpages/templates/staticpages/home.html`
   - Added "Data Deletion" link in the footer
   - Link appears alongside About, Privacy Policy, and Terms of Service

5. **Tests** - `tests/test_staticpages.py`
   - Added `test_data_deletion_page_loads()` test
   - Verifies page loads correctly and contains expected content

## Access Requirements

- **Authentication:** NOT required (publicly accessible)
- **SSL/HTTPS:** Required in production only
- **Redirects:** None (direct access allowed)

## Testing

### Run Tests
```bash
pytest tests/test_staticpages.py::TestStaticPages::test_data_deletion_page_loads -v
```

### All Static Pages Tests
```bash
pytest tests/test_staticpages.py -v
```

All tests are passing ✓

## Content Summary

The Data Deletion Policy covers:

1. **Who it applies to**
   - Merchants and businesses
   - Agents and staff
   - End customers

2. **What data can be deleted**
   - Account information
   - Transactional data (after retention period)
   - WhatsApp contact details
   - Other profile/usage data

3. **How to request deletion**
   - Email: support@emajinet.africa
   - Required information for request

4. **Processing timeline**
   - Target: 30 days for most requests

5. **Special provisions**
   - Legal retention requirements
   - Backup and log handling
   - Meta/WhatsApp integration compliance

## For Meta App Configuration

When configuring your Meta (WhatsApp/Facebook) app:

1. Go to your app settings in Meta Developer Console
2. Find the "Data Deletion Instructions URL" field
3. Enter your production URL:
   ```
   https://<your-domain>/home/data-deletion/
   ```
4. Save the configuration

## Contact Information

The policy directs users to email: **support@emajinet.africa**

Make sure this email address is monitored and can handle data deletion requests.

## Maintenance

- **Update Date:** The "Last updated" date is currently set to December 6, 2025
- Update this date when making changes to the policy
- Review policy periodically to ensure compliance with current laws

