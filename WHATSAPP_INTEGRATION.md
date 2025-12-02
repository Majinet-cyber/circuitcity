# WhatsApp Cloud API Integration

## Overview

This document describes the WhatsApp Cloud API integration implemented for the CircuitCity multi-tenant SaaS platform using Meta's Cloud API.

## What Was Implemented

### 1. WhatsApp Helper Module (`notifications/whatsapp.py`)

A clean, reusable helper module that:
- Reads credentials from environment variables (no hardcoded tokens)
- Provides `send_whatsapp_text(to_number, body)` function
- Raises `WhatsAppError` for better error handling
- Uses Meta's Cloud API v22.0

**Environment Variables Required:**
- `WHATSAPP_TOKEN` - Cloud API access token
- `WHATSAPP_PHONE_NUMBER_ID` - Phone number ID (e.g., 812090425331217)

### 2. Debug Test View (`/debug/whatsapp-test/`)

A staff-only internal testing page that:
- **Restricted to staff/superuser only** (403 for regular users)
- **GET**: Shows a simple form to enter a WhatsApp number
- **POST**: Sends a test message: "Emajinet test: your WhatsApp integration is live ✅"
- **Displays**:
  - Success message with JSON response on successful send
  - Clear error messages on failure
  - Environment variable status (safely truncated for security)

**Access:** `/debug/whatsapp-test/` (must be logged in as staff)

### 3. URL Configuration

- Created `core/urls_debug.py` with namespaced URLs (`app_name = "debug"`)
- Wired into main URLconf at `/debug/` path
- URL name: `debug:whatsapp_test`

### 4. Template (`templates/core/debug_whatsapp_test.html`)

- Extends `base.html` (consistent with app styling)
- Bootstrap 5 styling with proper form layout
- CSRF protection
- Success/error alert banners
- Shows environment configuration status

### 5. Dependencies

- Added `requests==2.32.3` to `requirements.txt`

### 6. Comprehensive Tests (`tests/test_debug_whatsapp.py`)

Nine test cases covering:
- ✅ Non-logged-in users redirected to login
- ✅ Normal (non-staff) users get 403
- ✅ Staff users can access GET
- ✅ Superusers can access GET
- ✅ Staff can POST successfully (mocked API)
- ✅ API errors handled gracefully
- ✅ Missing phone number validation
- ✅ Missing environment variables error
- ✅ Normal users cannot POST

**All tests pass!** (9/9)

## How to Use

### 1. Set Environment Variables

In your `.env` file:

```bash
WHATSAPP_TOKEN=your_cloud_api_token_here
WHATSAPP_PHONE_NUMBER_ID=812090425331217
WHATSAPP_BUSINESS_ACCOUNT_ID=25307886688822187
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Test the Integration

1. Run the development server:
   ```bash
   python manage.py runserver
   ```

2. Log in as a staff user

3. Navigate to: `http://localhost:8000/debug/whatsapp-test/`

4. Enter a WhatsApp number in international format (digits only, e.g., `265883596135`)

5. Click "Send Test Message"

6. Check your WhatsApp for the test message!

### 4. Using the Helper in Your Code

```python
from notifications.whatsapp import send_whatsapp_text, WhatsAppError

try:
    response = send_whatsapp_text("265883596135", "Hello from Emajinet!")
    print(f"Message sent: {response}")
except WhatsAppError as e:
    print(f"Failed to send: {e}")
```

## Security Notes

- ✅ No tokens or IDs are hardcoded
- ✅ All secrets read from environment variables
- ✅ Debug view restricted to staff/superuser only
- ✅ Token display truncated in UI for security
- ✅ CSRF protection on all POST requests

## Next Steps

As suggested in the original requirements:

1. **Rotate token in Meta Business Suite**:
   - Generate a new access token
   - Update `WHATSAPP_TOKEN` in your `.env`
   - Test again to confirm

2. **Implement webhook handler** for incoming messages

3. **Wire business events**:
   - Sale created → WhatsApp alert to manager
   - Low stock → WhatsApp alert
   - Commission earned → WhatsApp alert to agent
   - Profit milestones → WhatsApp celebration message

4. **Add your WhatsApp Business number** and start receiving real-time alerts

## Files Created/Modified

### Created:
- `notifications/whatsapp.py` - WhatsApp helper module
- `core/views_debug.py` - Debug views
- `core/urls_debug.py` - Debug URL configuration
- `templates/core/debug_whatsapp_test.html` - Test page template
- `tests/test_debug_whatsapp.py` - Comprehensive test suite
- `WHATSAPP_INTEGRATION.md` - This documentation

### Modified:
- `requirements.txt` - Added `requests==2.32.3`
- `cc/urls.py` - Added debug URL include

## Testing

Run the WhatsApp integration tests:

```bash
python -m pytest tests/test_debug_whatsapp.py -v
```

All 9 tests should pass ✅

## Support

For issues or questions about the WhatsApp integration:
- Check Meta's [Cloud API documentation](https://developers.facebook.com/docs/whatsapp/cloud-api)
- Review error logs in the debug view
- Verify environment variables are set correctly
- Ensure the phone number is in international format (digits only)

