# ADR-004: Capacitor for iOS/macOS Instead of Native Swift

## Status

Accepted (2026-02)

## Context

Aelu is a web-first application (Flask + Jinja2 templates + vanilla JavaScript). To provide a mobile experience on iOS and a native-feeling macOS app, we needed a strategy for deploying the web app as a native app with access to platform APIs (push notifications, audio recording, local storage).

## Decision Drivers

- Existing web app already provides the full feature set (dashboard, drills, reader, media shelf, listening, grammar)
- Solo developer: cannot maintain separate Swift/Kotlin codebases
- Need push notification support on iOS
- Need audio recording for tone production drills
- macOS app desirable but not at the cost of a separate codebase
- Users expect App Store distribution

## Considered Options

### Option 1: React Native

- **Pros**: Large ecosystem, good performance, extensive libraries
- **Cons**: Requires rewriting the entire UI in React Native (not a web wrapper), separate component library, significant development effort, solo developer cannot maintain web + RN codebases simultaneously

### Option 2: Flutter

- **Pros**: Single codebase for iOS/Android/web/desktop, strong performance, Dart is productive
- **Cons**: Requires full rewrite in Dart, web rendering uses Canvas (poor accessibility), different paradigm from existing Flask app, heavy SDK

### Option 3: Capacitor (chosen)

- **Pros**: Wraps existing web app in native WebView (WKWebView on iOS), plugin system for native APIs (push, audio, filesystem), same HTML/CSS/JS runs on web and native, minimal additional code, supports iOS and macOS from same project
- **Cons**: WebView performance ceiling, limited native API access compared to Swift, debugging requires understanding both web and native layers, 302 redirects open Safari instead of staying in WebView (requires workaround)

### Option 4: Native Swift

- **Pros**: Best performance, full platform API access, App Store review advantages
- **Cons**: Requires complete UI rewrite in SwiftUI/UIKit, separate codebase to maintain, solo developer bottleneck, Swift backend integration would be redundant with existing Flask API

## Decision

Use Capacitor to wrap the existing web application for iOS and macOS distribution. The web app runs on a remote Flask server, and the Capacitor shell connects to it using `server.url` configuration.

Architecture:
```
User -> Capacitor Shell (WKWebView) -> Flask Server (Fly.io or localhost)
                                    -> Native plugins (push, audio)
```

Key implementation details:
- `?native=1` query parameter detects native app context on the server side
- `render_template()` used instead of `redirect()` to avoid 302 redirects opening Safari
- `NSAllowsLocalNetworking` in Info.plist for HTTP localhost access during development
- Push tokens registered via Capacitor Push Notifications plugin and stored in `push_token` table

## Consequences

### Positive

- **Zero code duplication**: The same HTML/CSS/JS powers web, iOS, and macOS. A CSS change to the dashboard is immediately reflected on all platforms.
- **Rapid iteration**: New web features are instantly available on mobile without a separate build/deploy/review cycle.
- **Civic Sanctuary aesthetic preserved**: The warm stone + teal + terracotta design system with Cormorant Garamond headings and Noto Serif SC hanzi renders identically across platforms via CSS custom properties.
- **Native API access where needed**: Push notifications, audio recording for tone drills, and haptic feedback are available through Capacitor plugins.
- **App Store presence**: Users can install from the App Store, providing distribution credibility and push notification permissions.

### Negative

- **WebView performance**: Complex animations and transitions are slightly less smooth than native UIKit. Acceptable for Aelu's calm, deliberate UI but would be a problem for a game-like interface.
- **Redirect workaround**: Flask's `redirect()` function opens Safari instead of staying in WKWebView. Every redirect in auth flows and navigation must use `render_template()` with meta-refresh or JavaScript-based navigation. This is a persistent source of bugs.
- **Debugging complexity**: Issues may be in the web layer (JavaScript), the native layer (Swift/Capacitor), or the bridge between them. Console logs from WKWebView require Safari Web Inspector.
- **App Store review**: Apple occasionally scrutinizes WebView-only apps. Aelu's native plugin usage (push, audio) and custom UI should satisfy review requirements, but this is a risk.

### Lessons Learned

1. **CSP `upgrade-insecure-requests` breaks localhost**: This directive silently upgrades HTTP to HTTPS for all sub-resources (CSS, JS, fonts), causing them to fail to load. Only apply in production via `IS_PRODUCTION` flag.
2. **Server URL configuration**: Use `server.url` pointing to the production server with `?native=1` for detection. Do not use `server.url` pointing to localhost in production builds.
3. **ATS configuration**: Add `NSAllowsLocalNetworking` to Info.plist `NSAppTransportSecurity` for development builds that connect to HTTP localhost.
