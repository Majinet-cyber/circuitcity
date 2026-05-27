# TengaSale — Android Play Store Readiness

## Overview

TengaSale is a PWA (Progressive Web App) that can be published to the
Google Play Store using one of two approaches:

1. **TWA (Trusted Web Activity)** using Bubblewrap — recommended, fastest
2. **Capacitor** — for deeper native integration if needed later

---

## Option A: TWA with Bubblewrap (Recommended)

### Prerequisites

- Node.js ≥ 18
- Java 11+ and Android Studio
- A deployed TengaSale instance with HTTPS (required for TWA)

### Steps

1. **Install Bubblewrap**
   ```bash
   npm install -g @bubblewrap/cli
   ```

2. **Initialise the TWA project**
   ```bash
   mkdir tengasale-android && cd tengasale-android
   bubblewrap init --manifest https://tenga.africa/static/manifest.webmanifest
   ```
   When prompted:
   - **App name**: TengaSale
   - **Package name**: `africa.tenga.sale`
   - **Version**: 1
   - **Version name**: 1.0.0
   - **Signing key**: create a new keystore

3. **Build the APK/AAB**
   ```bash
   bubblewrap build
   ```
   Output: `app-release-bundle.aab` → upload to Play Console.

4. **Configure Digital Asset Links**
   Add to your web server at `https://tenga.africa/.well-known/assetlinks.json`:
   ```json
   [{
     "relation": ["delegate_permission/common.handle_all_urls"],
     "target": {
       "namespace": "android_app",
       "package_name": "africa.tenga.sale",
       "sha256_cert_fingerprints": ["<YOUR_KEYSTORE_FINGERPRINT>"]
     }
   }]
   ```

---

## Option B: Capacitor

1. **Install Capacitor**
   ```bash
   npm install @capacitor/core @capacitor/cli @capacitor/android
   npx cap init
   ```

2. **Config** (`capacitor.config.json`):
   ```json
   {
     "appId": "africa.tenga.sale",
     "appName": "TengaSale",
     "webDir": "dist",
     "server": {
       "url": "https://tenga.africa",
       "cleartext": false
     }
   }
   ```

3. **Add Android**
   ```bash
   npx cap add android
   npx cap sync
   npx cap open android
   ```
   Build and sign from Android Studio.

---

## Required Assets Checklist

| Asset | Size | Location |
|-------|------|----------|
| App icon | 192×192 px | `tengasale/static/images/icon-192.png` |
| App icon | 512×512 px | `tengasale/static/images/icon-512.png` |
| Maskable icon | 512×512 px | `tengasale/static/images/icon-512.png` |
| Adaptive icon foreground | 432×432 px | `tengasale/static/images/icon-fg.png` |
| Feature graphic | 1024×500 px | Create for Play Store listing |
| Screenshots (phone) | Min 2 | 390×844 recommended |

> **Note:** Icon files in `static/images/` are placeholders. Generate proper
> PNG icons from the TengaSaleLogo assets before publishing.

---

## Play Store Metadata Checklist

- [ ] App title: **TengaSale**
- [ ] Short description: "Smartphone financing made simple — Malawi"
- [ ] Full description: Explain phone financing, merchant app, payment portal
- [ ] Category: **Finance**
- [ ] Content rating: Complete IARC questionnaire (Finance → no issues expected)
- [ ] Privacy policy URL: `https://tenga.africa/privacy/`
- [ ] App icon (512×512 PNG, no transparency)
- [ ] Feature graphic (1024×500 PNG/JPG)
- [ ] Screenshots (2–8 phone screenshots, 390×844 recommended)
- [ ] Signing key stored securely (Google Play App Signing recommended)

---

## PWA Checklist (verify before packaging)

- [x] `manifest.webmanifest` served at `/static/manifest.webmanifest`
- [x] Service worker registered
- [x] `theme_color: #ff6a00`
- [x] `display: standalone`
- [x] Icon 192×192 and 512×512 defined in manifest
- [ ] HTTPS in production
- [ ] `assetlinks.json` deployed for TWA
- [ ] Offline fallback page at `/offline/`

---

## App Identity

| Field | Value |
|-------|-------|
| App ID | `africa.tenga.sale` |
| App Name | TengaSale |
| Version | 1.0.0 |
| Target Domain | `tenga.africa` |
| Payment Portal | `pay.tengasale.africa` |
