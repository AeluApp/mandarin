# Platform Asset Specifications

Required image assets for each target platform. All icons should be
generated from a single 1024x1024 source PNG.

Background color (light mode): `#F2EBE0` (--color-base)
Background color (dark mode): `#1C2028` (--color-base)

---

## iOS App Icons

Placed in the Xcode asset catalog (`ios/App/App/Assets.xcassets/AppIcon.appiconset/`).

| Size (px) | Scale | Usage                  |
|-----------|-------|------------------------|
| 20x20     | 1x    | Notification           |
| 40x40     | 2x    | Notification           |
| 60x60     | 3x    | Notification           |
| 29x29     | 1x    | Settings               |
| 58x58     | 2x    | Settings               |
| 87x87     | 3x    | Settings               |
| 40x40     | 1x    | Spotlight              |
| 80x80     | 2x    | Spotlight              |
| 120x120   | 3x    | Spotlight              |
| 120x120   | 2x    | App (iPhone)           |
| 180x180   | 3x    | App (iPhone)           |
| 76x76     | 1x    | App (iPad)             |
| 152x152   | 2x    | App (iPad)             |
| 167x167   | 2x    | App (iPad Pro)         |
| 1024x1024 | 1x    | App Store              |

Format: PNG, no transparency, no rounded corners (iOS applies the mask).

## iOS Splash Screens

Placed in `ios/App/App/Assets.xcassets/Splash.imageset/` or use a
storyboard-based splash (`LaunchScreen.storyboard`).

Preferred approach: a single-color storyboard with the Aelu logo centered.
The background color should match `--color-base` for each appearance mode.

| Asset               | Size (px)   |
|---------------------|-------------|
| splash-2732x2732    | 2732x2732   |
| splash-1334x1334    | 1334x1334   |

Format: PNG.

---

## Android App Icons

Placed in `android/app/src/main/res/`.

### Adaptive Icons (Android 8+)

Provide separate foreground and background layers:

| Directory        | Size (px) | Density |
|------------------|-----------|---------|
| mipmap-mdpi      | 108x108   | 1x      |
| mipmap-hdpi      | 162x162   | 1.5x    |
| mipmap-xhdpi     | 216x216   | 2x      |
| mipmap-xxhdpi    | 324x324   | 3x      |
| mipmap-xxxhdpi   | 432x432   | 4x      |

### Legacy Icons (pre-Android 8)

| Directory        | Size (px) | Density |
|------------------|-----------|---------|
| mipmap-mdpi      | 48x48     | 1x      |
| mipmap-hdpi      | 72x72     | 1.5x    |
| mipmap-xhdpi     | 96x96     | 2x      |
| mipmap-xxhdpi    | 144x144   | 3x      |
| mipmap-xxxhdpi   | 192x192   | 4x      |

### Play Store Listing

| Asset            | Size (px)   |
|------------------|-------------|
| play-store-icon  | 512x512     |

Format: PNG, 32-bit with alpha.

## Android Splash Screens

Placed in `android/app/src/main/res/drawable*/`.

| Directory        | Size (px)        |
|------------------|------------------|
| drawable-mdpi    | 480x320          |
| drawable-hdpi    | 800x480          |
| drawable-xhdpi   | 1280x720         |
| drawable-xxhdpi  | 1600x960         |
| drawable-xxxhdpi | 1920x1280        |

Also provide a `drawable/splash.xml` vector for Android 12+ splash.

Format: PNG or XML vector drawable.

---

## Desktop (Tauri)

Placed in `src-tauri/icons/`.

| File              | Size (px)   | Platform          |
|-------------------|-------------|-------------------|
| 32x32.png         | 32x32       | All (taskbar)     |
| 128x128.png       | 128x128     | All               |
| 128x128@2x.png    | 256x256     | macOS (Retina)    |
| icon.icns          | multi-size  | macOS             |
| icon.ico           | multi-size  | Windows           |

The `.icns` file should contain 16, 32, 128, 256, and 512 px variants.
The `.ico` file should contain 16, 32, 48, and 256 px variants.

Format: PNG source; `.icns` and `.ico` are generated from the PNGs.

---

## Web / PWA

These may already exist in `mandarin/web/static/`.

| File               | Size (px)   | Usage             |
|--------------------|-------------|-------------------|
| favicon.ico        | 48x48       | Browser tab       |
| icon-192.png       | 192x192     | PWA manifest      |
| icon-512.png       | 512x512     | PWA manifest      |
| apple-touch-icon   | 180x180     | iOS home screen   |
| og-image.png       | 1200x630    | Social sharing    |

Format: PNG (ICO for favicon).

---

## Generation workflow

1. Create a 1024x1024 master icon in the Civic Sanctuary style.
2. Use a tool such as `@capacitor/assets` or `tauri icon` to generate
   platform-specific sizes automatically.
3. Queue all generated assets for human review (per `CLAUDE.md` asset
   generation rules -- generated images are always `values_decision`).
