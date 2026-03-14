import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/core/deep_link_handler.dart';

void main() {
  group('DeepLinkHandler — aelu:// scheme', () {
    test('maps dashboard', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///dashboard'));
      expect(result, '/');
    });

    test('maps root', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///'));
      expect(result, '/');
    });

    test('maps session/full', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///session/full'));
      expect(result, '/session/full');
    });

    test('maps session/mini', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///session/mini'));
      expect(result, '/session/mini');
    });

    test('maps reading', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///reading'));
      expect(result, '/reading');
    });

    test('maps media', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///media'));
      expect(result, '/media');
    });

    test('maps listening', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///listening'));
      expect(result, '/listening');
    });

    test('maps settings', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///settings'));
      expect(result, '/settings');
    });

    test('maps payments', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///payments'));
      expect(result, '/payments');
    });

    test('maps referrals', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///referrals'));
      expect(result, '/referrals');
    });

    test('maps auth/login', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///auth/login'));
      expect(result, '/auth/login');
    });

    test('maps auth/register', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///auth/register'));
      expect(result, '/auth/register');
    });

    test('returns null for unknown path', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///unknown'));
      expect(result, isNull);
    });

    test('returns null for admin path', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('aelu:///admin'));
      expect(result, isNull);
    });
  });

  group('DeepLinkHandler — referral codes', () {
    test('maps valid referral to register', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///referral?code=ABC123'),
      );
      expect(result, '/auth/register');
    });

    test('accepts alphanumeric codes', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///referral?code=a1B2c3'),
      );
      expect(result, '/auth/register');
    });

    test('rejects code with special characters', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///referral?code=ABC-123'),
      );
      expect(result, isNull);
    });

    test('rejects code longer than 20 chars', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///referral?code=abcdefghijklmnopqrstuvwxyz'),
      );
      expect(result, isNull);
    });

    test('rejects empty code', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///referral?code='),
      );
      expect(result, isNull);
    });

    test('rejects referral without code param', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///referral'),
      );
      expect(result, isNull);
    });

    test('strips sensitive params from referral', () {
      // token param should be stripped by sanitizer
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///referral?code=ABC&token=secret'),
      );
      expect(result, '/auth/register');
    });
  });

  group('DeepLinkHandler — universal links', () {
    test('maps aeluapp.com/app/ path', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('https://aeluapp.com/app/reading'),
      );
      expect(result, '/reading');
    });

    test('maps aeluapp.com/app/session/full', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('https://aeluapp.com/app/session/full'),
      );
      expect(result, '/session/full');
    });

    test('maps aeluapp.com/app/dashboard to root', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('https://aeluapp.com/app/dashboard'),
      );
      expect(result, '/');
    });

    test('rejects wrong host', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('https://evil.com/app/dashboard'),
      );
      expect(result, isNull);
    });

    test('rejects subdomain of aeluapp.com', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('https://evil.aeluapp.com/app/dashboard'),
      );
      expect(result, isNull);
    });

    test('rejects path without /app/ prefix', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('https://aeluapp.com/dashboard'),
      );
      expect(result, isNull);
    });
  });

  group('DeepLinkHandler — scheme validation', () {
    test('rejects ftp scheme', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('ftp://aeluapp.com/app/dashboard'));
      expect(result, isNull);
    });

    test('rejects javascript scheme', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('javascript:alert(1)'));
      expect(result, isNull);
    });

    test('rejects data scheme', () {
      final result = DeepLinkHandler.mapUri(Uri.parse('data:text/html,<h1>hi</h1>'));
      expect(result, isNull);
    });

    test('accepts http scheme for universal links', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('http://aeluapp.com/app/settings'),
      );
      expect(result, '/settings');
    });
  });

  group('DeepLinkHandler — security edge cases', () {
    test('rejects path traversal', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///../../../etc/passwd'),
      );
      expect(result, isNull);
    });

    test('rejects null byte injection', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///dashboard%00admin'),
      );
      expect(result, isNull);
    });

    test('rejects encoded path traversal', () {
      final result = DeepLinkHandler.mapUri(
        Uri.parse('aelu:///%2e%2e/etc/passwd'),
      );
      expect(result, isNull);
    });
  });
}
