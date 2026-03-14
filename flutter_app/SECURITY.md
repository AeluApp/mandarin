# Aelu Mobile App — Security Configuration

## Release Build Commands

### Flutter Obfuscation (OWASP M9, CIS 7.1)

```bash
# iOS release
flutter build ios --release --obfuscate --split-debug-info=build/debug-info/

# Android release
flutter build appbundle --release --obfuscate --split-debug-info=build/debug-info/

# Android APK (if needed)
flutter build apk --release --obfuscate --split-debug-info=build/debug-info/
```

The `--split-debug-info` flag stores debug symbols separately for crash symbolication
without including them in the release binary.

## Pre-Release Security Checklist

### Certificate Pinning
- [ ] Update SHA-256 SPKI hashes in `lib/core/security/security_config.dart`
- [ ] Update pin hashes in `android/app/src/main/res/xml/network_security_config.xml`
- [ ] Test with production certificate
- [ ] Verify backup pin works for rotation

### Signing
- [ ] Replace debug signing config in `android/app/build.gradle.kts` with release keystore
- [ ] Configure iOS signing with distribution certificate
- [ ] Store signing keys in secure CI/CD secrets (never in repo)

### Environment
- [ ] Set `API_URL` to production: `--dart-define=API_URL=https://aeluapp.com`
- [ ] Verify no `http://` URLs in codebase (except localhost exceptions)
- [ ] Remove iOS localhost ATS exception for App Store submission

### Data Protection
- [ ] Verify `android:allowBackup="false"` in AndroidManifest.xml
- [ ] Verify ATS enforced in Info.plist (`NSAllowsArbitraryLoads=false`)
- [ ] Verify all tokens use FlutterSecureStorage (Keychain/KeyStore)
- [ ] Verify no sensitive data in SharedPreferences

### Network
- [ ] Verify cleartext traffic blocked (network_security_config.xml)
- [ ] Verify WebSocket uses first-message auth (not URL query params)
- [ ] Test certificate pinning rejects invalid certs

### Authentication
- [ ] Verify rate limiting on login (5 attempts, exponential backoff)
- [ ] Verify rate limiting on MFA (3 attempts, stricter lockout)
- [ ] Verify session timeout after 30 minutes idle
- [ ] Verify background timeout after 15 minutes
- [ ] Verify MFA route cannot be bypassed via direct navigation

### Error Handling
- [ ] Verify stack traces truncated to 5 frames
- [ ] Verify local file paths stripped from error reports
- [ ] Verify PII scrubbed from analytics events
- [ ] Verify generic error messages shown to users (no stack traces)

### Platform
- [ ] Verify FLAG_SECURE on Android auth screens
- [ ] Verify blur overlay on iOS task switcher
- [ ] Verify ProGuard/R8 enabled for Android release
- [ ] Run `flutter build` with `--obfuscate`

## Framework Compliance Matrix

| Control | OWASP | NIST | ISO 27001 | CIS |
|---------|-------|------|-----------|-----|
| Cert pinning | M3 | SC-8 | A.13.1.1 | 6.1 |
| Encrypted storage | M2 | SC-28 | A.10.1.1 | 2.1 |
| Token in URL prevention | M3 | IA-5 | A.9.4.2 | 3.1 |
| Rate limiting | M4 | AC-7 | A.9.4.2 | 3.2 |
| MFA enforcement | M4 | IA-2 | A.9.4.2 | 3.3 |
| Session timeout | M1 | AC-12 | A.11.2.8 | 4.5 |
| Screenshot prevention | M9 | — | A.11.2.9 | 4.3 |
| Deep link validation | M1 | AC-3 | A.14.1.2 | 5.2 |
| PII scrubbing | — | SI-11 | A.18.1.4 | — |
| Stack trace sanitization | M9 | SI-11 | A.12.4.1 | 7.2 |
| Cleartext blocking | M3 | SC-8 | A.13.1.1 | 6.1 |
| Code obfuscation | M9 | — | — | 7.1 |
| Backup prevention | M2 | — | A.11.2.7 | 2.1 |
| Input validation | M4 | SI-10 | A.14.1.2 | 5.1 |
| Content hiding (task switcher) | M9 | — | A.11.2.9 | 4.3 |
| Auto-redirect follow disabled | M3 | — | A.13.1.1 | 6.2 |
| Token refresh mutex | — | IA-5 | A.9.4.2 | 3.1 |
| Message size validation | M4 | SI-10 | A.14.1.3 | 5.1 |
| Heartbeat/stale connection detection | M3 | SC-10 | A.13.1.1 | 6.3 |
