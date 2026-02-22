# App Store Submission Checklist

## Apple App Store (iOS)

### Prerequisites
- [ ] Apple Developer Program enrollment ($99/year)
- [ ] App Store Connect account set up
- [ ] Provisioning profile + signing certificate created in Xcode
- [ ] Bundle ID registered: `com.mandarinapp.app`

### Build & Sign
- [ ] Archive build in Xcode (Product → Archive)
- [ ] Code signing with distribution certificate
- [ ] Bitcode enabled (or disabled if not needed)
- [ ] Minimum deployment target set (iOS 16.0+)

### App Store Connect Setup
- [ ] App name: "Mandarin"
- [ ] Subtitle: "Patient Mandarin study"
- [ ] Primary category: Education
- [ ] Secondary category: Reference
- [ ] Age rating: 4+ (no objectionable content)
- [ ] Pricing: Free (with in-app subscription)

### Required Assets
- [ ] App icon: 1024x1024 PNG (no alpha, no rounded corners)
- [ ] Screenshots (at least one set):
  - [ ] 6.7" (1290x2796) — iPhone 15 Pro Max
  - [ ] 6.5" (1284x2778) — iPhone 14 Plus
  - [ ] 5.5" (1242x2208) — iPhone 8 Plus
  - [ ] iPad Pro 12.9" (2048x2732) — if supporting iPad
- [ ] App preview video (optional, 15-30 seconds)

### Metadata
- [ ] Description (from `/marketing/app-store/ios-metadata.md`)
- [ ] Keywords (100 char max, comma-separated)
- [ ] Support URL
- [ ] Marketing URL (optional)
- [ ] Privacy policy URL (required): link to `/marketing/landing/privacy.html`

### Privacy Declarations
- [ ] App Privacy: Data collection disclosure
  - Data collected: email, usage data (drill results)
  - Purpose: app functionality
  - Not linked to identity: analytics
- [ ] NSMicrophoneUsageDescription in Info.plist
- [ ] Push notification entitlement

### TestFlight
- [ ] Upload build via Xcode or Transporter
- [ ] Add internal testers
- [ ] Add external testers (requires Beta App Review)
- [ ] Test on physical devices (iPhone + iPad if applicable)
- [ ] Verify in-app purchases work in sandbox

### Submission
- [ ] Submit for App Review
- [ ] Respond to any review feedback
- [ ] Set release date (manual or automatic)

---

## Google Play Store (Android)

### Prerequisites
- [ ] Google Play Console account ($25 one-time)
- [ ] App created in Play Console
- [ ] Signing key set up (Play App Signing recommended)

### Build
- [ ] Generate signed AAB (Android App Bundle)
- [ ] Min SDK: API 24 (Android 7.0)
- [ ] Target SDK: API 34 (Android 14)

### Play Console Setup
- [ ] App name: "Mandarin"
- [ ] Short description (80 chars max)
- [ ] Full description (4000 chars max)
- [ ] Category: Education
- [ ] Tags: Language learning, Mandarin, Chinese

### Required Assets
- [ ] App icon: 512x512 PNG (32-bit, no alpha)
- [ ] Feature graphic: 1024x500 PNG/JPG
- [ ] Screenshots (2-8 per device type):
  - [ ] Phone: 1080x1920 minimum
  - [ ] Tablet 7": 1200x1920 (if supporting)
  - [ ] Tablet 10": 1920x1200 (if supporting)

### Content Rating
- [ ] Complete IARC rating questionnaire
- [ ] Expected rating: Everyone / PEGI 3

### Privacy & Compliance
- [ ] Privacy policy URL
- [ ] Data safety section:
  - Data collected: email, app interactions
  - Data shared: none
  - Security: data encrypted in transit
- [ ] Ads declaration: no ads
- [ ] Target audience: general (not children-specific)

### Testing
- [ ] Internal testing track: upload AAB
- [ ] Closed testing: invite testers
- [ ] Open testing: optional broader beta
- [ ] Test on multiple screen sizes
- [ ] Verify in-app purchases with test accounts

### Release
- [ ] Production release
- [ ] Staged rollout (recommended: start at 10%)
- [ ] Monitor crash reports in Play Console
- [ ] Respond to any policy violations
