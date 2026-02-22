# Mandarin Mobile (Capacitor)

Wraps the Mandarin web app as a native iOS/Android app using Capacitor.

## Prerequisites

- Node.js 18+
- Xcode 15+ (iOS) or Android Studio (Android)
- Apple Developer account (iOS distribution)

## Setup

```bash
cd mobile
npm install

# Generate iOS project
npx cap add ios

# Generate Android project
npx cap add android
```

## Generate App Icons & Splash Screens

Place source files in `resources/`:
- `icon.png` — 1024x1024 app icon
- `splash.png` — 2732x2732 splash screen (warm stone bg #F2EBE0 + centered logo)

```bash
./generate-assets.sh
```

## iOS Configuration

After generating the iOS project:

1. Open Xcode: `npx cap open ios`
2. Set Bundle ID: `com.mandarinapp.app`
3. Set deployment target: iOS 16.0+
4. Add Info.plist keys from `ios-plist-additions.xml`
5. Configure signing (Team, Provisioning Profile)

## Development

Point to local dev server:

```bash
CAPACITOR_SERVER_URL=http://localhost:5173 npx cap sync
npx cap open ios
```

## Build & Deploy

```bash
# Sync web assets to native projects
npx cap sync

# Open in Xcode for archive + distribution
npx cap open ios

# Or open in Android Studio
npx cap open android
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run sync` | Sync web assets to native projects |
| `npm run ios` | Open iOS project in Xcode |
| `npm run android` | Open Android project in Android Studio |
| `npm run build` | Sync + open iOS |

## Health Check

```bash
npx cap doctor
```

## App Store Submission

See `store-assets/submission-checklist.md` for step-by-step instructions for both Apple App Store and Google Play Store.
