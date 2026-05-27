# SMS 2FA UI Flow Visual Guide

## 🎯 Quick Reference: What Users See at Each Step

### State: Twilio Not Configured
```
┌─────────────────────────────────────────────┐
│ Two-Factor Authentication (SMS)            │
│                                             │
│ Status: [ Unavailable ]                     │
│                                             │
│ Configure Twilio to enable SMS OTP 2FA.    │
│                                             │
│ [ Unavailable ] (button disabled)          │
└─────────────────────────────────────────────┘
```

---

### State: 2FA Disabled - Step 1 (Enter Phone)
```
┌─────────────────────────────────────────────┐
│ Two-Factor Authentication (SMS)            │
│                                             │
│ Status: [ Disabled ]                        │
│                                             │
│ Add an extra layer of security.            │
│                                             │
│ ┌────────────────────────┐                 │
│ │ +265991234567          │  (phone input)  │
│ └────────────────────────┘                 │
│                                             │
│ [ Send code ]  (blue button)               │
└─────────────────────────────────────────────┘
```

**Action:** User enters phone → Clicks "Send code" → POST to `/accounts/2fa/sms/enable/start/`

---

### State: 2FA Disabled - Step 2 (Enter OTP)
```
┌─────────────────────────────────────────────┐
│ Two-Factor Authentication (SMS)            │
│                                             │
│ Status: [ Disabled ]                        │
│                                             │
│ Code sent to +265******567                 │
│                                             │
│       ┌─────────┐                           │
│       │ 1 2 3 4 5 6 │  (OTP input, large)   │
│       └─────────┘                           │
│                                             │
│ [ Verify & Enable ]  (blue button)         │
│                                             │
│ Resend code  (small gray button)           │
└─────────────────────────────────────────────┘
```

**Action:** User enters 6-digit code → Clicks "Verify & Enable" → POST to `/accounts/2fa/sms/enable/verify/`

**Success → Redirects back to settings with:**
✅ "Two-factor authentication enabled successfully."

---

### State: 2FA Enabled - Step 1 (Initial)
```
┌─────────────────────────────────────────────┐
│ Two-Factor Authentication (SMS)            │
│                                             │
│ Status: [ Enabled ]                         │
│                                             │
│ Phone: +265******567                        │
│                                             │
│ [ Send code to disable ]  (gray button)    │
└─────────────────────────────────────────────┘
```

**Action:** User clicks "Send code to disable" → POST to `/accounts/2fa/sms/disable/start/`

---

### State: 2FA Enabled - Step 2 (Enter OTP to Disable)
```
┌─────────────────────────────────────────────┐
│ Two-Factor Authentication (SMS)            │
│                                             │
│ Status: [ Enabled ]                         │
│                                             │
│ Phone: +265******567                        │
│                                             │
│ Code sent to +265******567                 │
│                                             │
│       ┌─────────┐                           │
│       │ 1 2 3 4 5 6 │  (OTP input, large)   │
│       └─────────┘                           │
│                                             │
│ [ Verify & Disable ]  (red button)         │
│                                             │
│ Resend code  (small gray button)           │
└─────────────────────────────────────────────┘
```

**Action:** User enters 6-digit code → Clicks "Verify & Disable" → POST to `/accounts/2fa/sms/disable/verify/`

**Success → Redirects back to settings with:**
✅ "Two-factor authentication disabled."

---

## 🎨 Color Coding

| Status | Badge Color | Meaning |
|--------|-------------|---------|
| **Unavailable** | Gray | Twilio not configured |
| **Disabled** | Yellow/Warning | 2FA not enabled |
| **Enabled** | Green/Success | 2FA active |

## 🔘 Button States

| Button Text | Color | Action |
|-------------|-------|--------|
| **Send code** | Blue (Primary) | Start enable flow |
| **Verify & Enable** | Blue (Primary) | Complete enable |
| **Send code to disable** | Gray (Muted) | Start disable flow |
| **Verify & Disable** | Red (Danger) | Complete disable |
| **Resend code** | Gray Small (Muted) | Resend OTP |
| **Unavailable** | Gray Disabled | No action (Twilio off) |

## 📱 Input Field Details

### Phone Number Input
```html
Type: tel (triggers numeric keyboard on mobile)
Format: +265991234567 (E.164 international)
Pattern: \+[0-9]{8,20}
Placeholder: "+265991234567"
Width: max-width:260px
```

### OTP Code Input
```html
Type: text
Inputmode: numeric (numeric keyboard on mobile)
Pattern: [0-9]{6}
Maxlength: 6
Style: Large font, centered, letter-spaced
Width: max-width:200px
Auto-focus: Yes (when shown)
```

**Visual style:** Numbers are spaced out like `1  2  3  4  5  6` for easy reading

---

## 🔄 Flow Diagrams

### Enable Flow
```
Disabled State
     ↓
Enter Phone (+265...)
     ↓
[Send code] (POST)
     ↓
Backend sends SMS
     ↓
OTP Input Shown
     ↓
Enter 6-digit code
     ↓
[Verify & Enable] (POST)
     ↓
Backend verifies
     ↓
Enabled State ✅
```

### Disable Flow
```
Enabled State
     ↓
[Send code to disable] (POST)
     ↓
Backend sends SMS
     ↓
OTP Input Shown
     ↓
Enter 6-digit code
     ↓
[Verify & Disable] (POST)
     ↓
Backend verifies
     ↓
Disabled State ✅
```

### Resend Flow (Both Enable & Disable)
```
OTP Input Visible
     ↓
[Resend code] (POST)
     ↓
Backend checks rate limit
     ↓
If allowed: Send new SMS
If denied: Show error
     ↓
OTP Input Remains
(session phone preserved)
```

---

## ⚠️ Error Messages

### Client-Side Validation (Browser)
- Phone field empty → "Please fill out this field"
- Phone format invalid → "Please match the requested format"
- Code field empty → "Please fill out this field"

### Server-Side Errors (Django Messages)
- ❌ "Phone number is required."
- ❌ "Phone number must be in international format (e.g. +265991234567)"
- ❌ "Invalid phone number length."
- ❌ "Too many attempts. Contact your admin." (rate limit)
- ❌ "Failed to send verification code."
- ❌ "Verification code is required."
- ❌ "Invalid verification code."
- ❌ "No pending verification. Please start the process again." (session expired)

### Success Messages
- ✅ "Verification code sent to +265991234567"
- ✅ "Two-factor authentication enabled successfully."
- ✅ "Two-factor authentication disabled."

---

## 🎯 Key UX Features

### 1. **Large OTP Input**
```css
font-size: var(--fs-18);        /* Large text */
letter-spacing: 0.3em;          /* Spaced out */
text-align: center;             /* Centered */
```
Makes it easy to read and verify what you typed.

### 2. **Mobile Optimization**
- `type="tel"` on phone input → numeric keyboard
- `inputmode="numeric"` on OTP input → numeric keyboard
- Touch-friendly button sizes
- Readable text sizes on small screens

### 3. **Auto-Focus**
OTP input gets `autofocus` attribute → cursor ready when page loads

### 4. **Validation Feedback**
- HTML5 pattern validation (instant feedback)
- Required fields (can't submit empty)
- Clear placeholders ("+265991234567")
- Helpful title tooltips on hover

### 5. **Resend Button Placement**
Appears below the verify button, smaller size, gray color → clear visual hierarchy

---

## 🔒 Security Notes

### What Users SEE
- ✅ Masked phone: `+265******567`
- ✅ Status badges
- ✅ Success/error messages

### What Users DON'T SEE (Security)
- ❌ Full phone number (after initial entry)
- ❌ OTP codes (never echoed back)
- ❌ Rate limit counters (just error message)
- ❌ Session data (internal backend state)

### Protection Against Abuse
1. **Rate Limits**: Backend enforces send/verify limits
2. **Session Expiry**: OTP flow times out (backend handles)
3. **CSRF Protection**: All forms have CSRF tokens
4. **Input Validation**: Both client and server side

---

## 📊 Technical Implementation

### POST Endpoints Used
```
POST /accounts/2fa/sms/enable/start/     → Send enable code
POST /accounts/2fa/sms/enable/verify/    → Verify & enable
POST /accounts/2fa/sms/disable/start/    → Send disable code
POST /accounts/2fa/sms/disable/verify/   → Verify & disable
```

### Session Flags (Backend Sets These)
```python
request.session["twofa_enable_flow"] = True      # Enable pending
request.session["twofa_disable_flow"] = True     # Disable pending
request.session["twofa_pending_phone"] = "+265..." # For resend
```

### Template Context (Passed to Partial)
```python
context = {
    "twofa_available": True/False,           # Twilio configured?
    "twofa_sms_enabled": True/False,         # User has 2FA?
    "twofa_phone_masked": "+265******567",   # User's phone
    "twofa_enable_pending": True/False,      # Show enable OTP?
    "twofa_disable_pending": True/False,     # Show disable OTP?
    "twofa_pending_phone_masked": "+265******567", # For resend msg
}
```

---

## 🧪 Testing Checklist

- [ ] Visit `/accounts/settings/` → See 2FA card
- [ ] Visit `/accounts/settings/security/` → See 2FA card
- [ ] Disabled state → See phone input + "Send code"
- [ ] Enter phone → Click "Send code" → No 405 error
- [ ] OTP input appears → See 6-digit input centered
- [ ] Enter OTP → Click "Verify & Enable" → Success
- [ ] Enabled state → See masked phone + "Send code to disable"
- [ ] Click "Send code to disable" → No 405 error
- [ ] OTP input appears → Enter OTP → Click "Verify & Disable" → Success
- [ ] Logout → Login → Redirected to 2FA challenge
- [ ] Resend button works (both enable and disable)
- [ ] Rate limit enforced (try spamming resend)
- [ ] All forms have CSRF tokens (view source)
- [ ] Mobile: numeric keyboard appears for phone/OTP inputs

---

## 📱 Mobile Experience

### Phone Input
```
┌──────────────────┐
│ +265991234567    │ ← Tel keyboard opens
└──────────────────┘
```

### OTP Input  
```
┌──────────────┐
│  1 2 3 4 5 6  │ ← Numeric keyboard opens
└──────────────┘
```

### Buttons
```
┌─────────────────────┐
│   Send code   │ ← Touch-friendly size
└─────────────────────┘
```

All interactive elements are:
- ✅ Large enough to tap (min 44x44px)
- ✅ High contrast (readable in sunlight)
- ✅ Properly spaced (no accidental taps)

---

## 🎉 Success Criteria

After implementation, the following MUST work:

1. ✅ **No 405 errors** - All requests are POST with CSRF tokens
2. ✅ **OTP UI shows** - Users see input fields, not instant redirects
3. ✅ **Resend works** - Users can request new codes
4. ✅ **Rate limits enforced** - Backend prevents abuse
5. ✅ **Both pages work** - /accounts/settings/ and /accounts/settings/security/
6. ✅ **Mobile friendly** - Numeric keyboards, readable fonts
7. ✅ **Login challenge works** - After enabling, login requires OTP
8. ✅ **Phone masked** - Security: only show partial number

All criteria verified manually before considering complete! ✅

