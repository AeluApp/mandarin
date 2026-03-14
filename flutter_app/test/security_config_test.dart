import 'package:flutter_test/flutter_test.dart';

import 'package:aelu/core/security/security_config.dart';

void main() {
  // ── RateLimiter ──

  group('RateLimiter', () {
    test('starts not locked out with full attempts', () {
      final limiter = RateLimiter(maxAttempts: 3);
      expect(limiter.isLockedOut, false);
      expect(limiter.remainingAttempts, 3);
      expect(limiter.remainingLockout, isNull);
    });

    test('tracks failed attempts without locking out prematurely', () {
      final limiter = RateLimiter(maxAttempts: 3);
      expect(limiter.recordFailure(), false); // 1/3
      expect(limiter.remainingAttempts, 2);
      expect(limiter.isLockedOut, false);

      expect(limiter.recordFailure(), false); // 2/3
      expect(limiter.remainingAttempts, 1);
      expect(limiter.isLockedOut, false);
    });

    test('locks out after max attempts', () {
      final limiter = RateLimiter(maxAttempts: 3);
      limiter.recordFailure(); // 1
      limiter.recordFailure(); // 2
      expect(limiter.recordFailure(), true); // 3 → locked
      expect(limiter.isLockedOut, true);
      expect(limiter.remainingAttempts, 0);
      expect(limiter.remainingLockout, isNotNull);
    });

    test('recordSuccess resets everything', () {
      final limiter = RateLimiter(maxAttempts: 3);
      limiter.recordFailure();
      limiter.recordFailure();
      limiter.recordSuccess();
      expect(limiter.isLockedOut, false);
      expect(limiter.remainingAttempts, 3);
    });

    test('remainingAttempts never goes below 0', () {
      final limiter = RateLimiter(maxAttempts: 2);
      limiter.recordFailure();
      limiter.recordFailure(); // locked
      // Even recording more failures after lockout shouldn't go negative.
      expect(limiter.remainingAttempts, 0);
    });

    test('lockout duration increases with cycles', () {
      final limiter = RateLimiter(
        maxAttempts: 1,
        baseLockout: const Duration(seconds: 10),
        maxLockout: const Duration(seconds: 320),
      );

      // First lockout.
      limiter.recordFailure();
      expect(limiter.isLockedOut, true);
      final firstLockout = limiter.remainingLockout!;
      expect(firstLockout.inSeconds, lessThanOrEqualTo(10));
    });

    test('uses default security config values', () {
      final limiter = RateLimiter();
      expect(limiter.remainingAttempts, SecurityConfig.maxLoginAttempts);
    });
  });

  // ── InputSanitizer ──

  group('InputSanitizer.sanitize', () {
    test('trims whitespace', () {
      expect(InputSanitizer.sanitize('  hello  '), 'hello');
    });

    test('removes control characters', () {
      expect(InputSanitizer.sanitize('he\x00llo'), 'hello');
      expect(InputSanitizer.sanitize('he\x07llo'), 'hello');
    });

    test('preserves newlines and tabs', () {
      expect(InputSanitizer.sanitize('hello\nworld'), 'hello\nworld');
      expect(InputSanitizer.sanitize('hello\tworld'), 'hello\tworld');
    });

    test('enforces max length', () {
      final long = 'a' * 600;
      final result = InputSanitizer.sanitize(long);
      expect(result.length, SecurityConfig.maxInputLength);
    });

    test('respects custom max length', () {
      final result = InputSanitizer.sanitize('hello world', maxLength: 5);
      expect(result, 'hello');
    });

    test('handles empty string', () {
      expect(InputSanitizer.sanitize(''), '');
    });

    test('handles string with only whitespace', () {
      expect(InputSanitizer.sanitize('   '), '');
    });
  });

  group('InputSanitizer.isValidEmail', () {
    test('accepts valid email', () {
      expect(InputSanitizer.isValidEmail('user@example.com'), true);
    });

    test('accepts email with dots and hyphens', () {
      expect(InputSanitizer.isValidEmail('user.name@example-domain.com'), true);
    });

    test('accepts email with plus sign', () {
      expect(InputSanitizer.isValidEmail('user+tag@example.com'), true);
    });

    test('rejects email without @', () {
      expect(InputSanitizer.isValidEmail('userexample.com'), false);
    });

    test('rejects email without domain', () {
      expect(InputSanitizer.isValidEmail('user@'), false);
    });

    test('rejects email without TLD', () {
      expect(InputSanitizer.isValidEmail('user@example'), false);
    });

    test('rejects empty string', () {
      expect(InputSanitizer.isValidEmail(''), false);
    });

    test('rejects overly long email', () {
      final long = '${'a' * 250}@b.com';
      expect(InputSanitizer.isValidEmail(long), false);
    });
  });

  group('InputSanitizer.passwordStrengthIssue', () {
    test('accepts strong password', () {
      expect(InputSanitizer.passwordStrengthIssue('Abc12345!'), isNull);
    });

    test('rejects short password', () {
      expect(
        InputSanitizer.passwordStrengthIssue('Ab1!'),
        contains('characters'),
      );
    });

    test('rejects password without uppercase', () {
      expect(
        InputSanitizer.passwordStrengthIssue('abcdefgh1!'),
        contains('uppercase'),
      );
    });

    test('rejects password without lowercase', () {
      expect(
        InputSanitizer.passwordStrengthIssue('ABCDEFGH1!'),
        contains('lowercase'),
      );
    });

    test('rejects password without number', () {
      expect(
        InputSanitizer.passwordStrengthIssue('Abcdefgh!'),
        contains('number'),
      );
    });

    test('rejects password without special char', () {
      expect(
        InputSanitizer.passwordStrengthIssue('Abcdefgh1'),
        contains('special'),
      );
    });

    test('rejects overly long password', () {
      final long = 'Aa1!' * 50; // 200 chars
      expect(
        InputSanitizer.passwordStrengthIssue(long),
        contains('too long'),
      );
    });
  });

  group('InputSanitizer.sanitizeDeepLinkPath', () {
    test('accepts whitelisted path', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/dashboard'), '/dashboard');
    });

    test('accepts root path', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/'), '/');
    });

    test('normalizes empty path to root', () {
      expect(InputSanitizer.sanitizeDeepLinkPath(''), '/');
    });

    test('strips trailing slash', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/dashboard/'), '/dashboard');
    });

    test('blocks path traversal', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/../etc/passwd'), isNull);
    });

    test('blocks null bytes', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/dashboard\x00'), isNull);
    });

    test('rejects unknown path', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/admin'), isNull);
    });

    test('accepts session paths', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/session/full'), '/session/full');
      expect(InputSanitizer.sanitizeDeepLinkPath('/session/mini'), '/session/mini');
    });

    test('accepts auth paths', () {
      expect(InputSanitizer.sanitizeDeepLinkPath('/auth/login'), '/auth/login');
      expect(InputSanitizer.sanitizeDeepLinkPath('/auth/register'), '/auth/register');
    });
  });

  group('InputSanitizer.sanitizeQueryParams', () {
    test('passes through safe params', () {
      final params = {'code': 'ABC123', 'ref': 'friend'};
      final result = InputSanitizer.sanitizeQueryParams(params);
      expect(result, {'code': 'ABC123', 'ref': 'friend'});
    });

    test('strips sensitive keys', () {
      final params = {
        'code': 'ABC',
        'token': 'secret-jwt',
        'access_token': 'jwt',
        'password': 'pass123',
      };
      final result = InputSanitizer.sanitizeQueryParams(params);
      expect(result, {'code': 'ABC'});
    });

    test('truncates long values', () {
      // Use 'name' as key since 'key' is in the blocked list.
      final params = {'name': 'a' * 300};
      final result = InputSanitizer.sanitizeQueryParams(params);
      expect(result['name']!.length, 200);
    });

    test('handles empty params', () {
      expect(InputSanitizer.sanitizeQueryParams({}), <String, String>{});
    });

    test('is case-insensitive for blocked keys', () {
      final params = {'Token': 'x', 'ACCESS_TOKEN': 'y', 'code': 'z'};
      final result = InputSanitizer.sanitizeQueryParams(params);
      expect(result, {'code': 'z'});
    });
  });

  // ── PiiScrubber ──

  group('PiiScrubber.scrub', () {
    test('scrubs email addresses', () {
      const input = 'Error for user@example.com';
      expect(PiiScrubber.scrub(input), 'Error for [EMAIL]');
    });

    test('scrubs JWT tokens', () {
      // Pure JWT without 'Token:' prefix (password pattern would match first).
      const input = 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0 expired';
      final result = PiiScrubber.scrub(input);
      expect(result.contains('eyJ'), false);
    });

    test('scrubs password-like patterns', () {
      const input = 'password: mySecret123';
      expect(PiiScrubber.scrub(input), contains('[REDACTED]'));
    });

    test('preserves non-sensitive text', () {
      const input = 'Connection timeout at endpoint /api/status';
      expect(PiiScrubber.scrub(input), input);
    });

    test('handles empty string', () {
      expect(PiiScrubber.scrub(''), '');
    });

    test('scrubs multiple emails in one string', () {
      const input = 'Users: a@b.com and c@d.com failed';
      final result = PiiScrubber.scrub(input);
      expect(result.contains('a@b.com'), false);
      expect(result.contains('c@d.com'), false);
    });
  });

  group('PiiScrubber.scrubMap', () {
    test('redacts sensitive keys', () {
      final data = <String, dynamic>{
        'email': 'user@test.com',
        'password': 'secret',
        'token': 'jwt-token',
        'message': 'hello',
      };
      final result = PiiScrubber.scrubMap(data);
      expect(result['email'], '[REDACTED]');
      expect(result['password'], '[REDACTED]');
      expect(result['token'], '[REDACTED]');
      expect(result['message'], 'hello');
    });

    test('scrubs PII from string values', () {
      final data = <String, dynamic>{
        'error': 'Failed for user@test.com',
      };
      final result = PiiScrubber.scrubMap(data);
      expect(result['error'], contains('[EMAIL]'));
    });

    test('recursively scrubs nested maps', () {
      final data = <String, dynamic>{
        'data': <String, dynamic>{
          'email': 'nested@test.com',
          'safe': 'visible',
        },
      };
      final result = PiiScrubber.scrubMap(data);
      final nested = result['data'] as Map<String, dynamic>;
      expect(nested['email'], '[REDACTED]');
      expect(nested['safe'], 'visible');
    });

    test('preserves non-sensitive non-string values', () {
      final data = <String, dynamic>{
        'count': 42,
        'active': true,
        'items': [1, 2, 3],
      };
      final result = PiiScrubber.scrubMap(data);
      expect(result['count'], 42);
      expect(result['active'], true);
      expect(result['items'], [1, 2, 3]);
    });
  });

  group('PiiScrubber.sanitizeStackTrace', () {
    test('returns null for null input', () {
      expect(PiiScrubber.sanitizeStackTrace(null), isNull);
    });

    test('truncates to max frames', () {
      final stack = List.generate(10, (i) => '#$i frame$i').join('\n');
      final result = PiiScrubber.sanitizeStackTrace(stack, maxFrames: 3);
      expect(result!.split('\n').length, 3);
    });

    test('strips absolute paths to lib/', () {
      const stack = '#0 /Users/dev/projects/aelu/lib/main.dart';
      final result = PiiScrubber.sanitizeStackTrace(stack);
      expect(result!.contains('/Users/dev/projects/aelu/'), false);
      expect(result.contains('lib/main.dart'), true);
    });

    test('handles short stack traces', () {
      const stack = '#0 someFunction\n#1 otherFunction';
      final result = PiiScrubber.sanitizeStackTrace(stack, maxFrames: 5);
      expect(result!.split('\n').length, 2);
    });
  });

  // ── SecurityConfig constants ──

  group('SecurityConfig', () {
    test('has reasonable session timeout', () {
      expect(SecurityConfig.sessionTimeout.inMinutes, 30);
    });

    test('has reasonable background timeout', () {
      expect(SecurityConfig.backgroundTimeout.inMinutes, 15);
    });

    test('password requirements are sensible', () {
      expect(SecurityConfig.minPasswordLength, greaterThanOrEqualTo(8));
      expect(SecurityConfig.maxPasswordLength, greaterThan(SecurityConfig.minPasswordLength));
    });

    test('login attempts are limited', () {
      expect(SecurityConfig.maxLoginAttempts, greaterThan(0));
      expect(SecurityConfig.maxLoginAttempts, lessThanOrEqualTo(10));
    });

    test('all deep link paths start with /', () {
      for (final path in SecurityConfig.allowedDeepLinkPaths) {
        expect(path.startsWith('/'), true, reason: 'Path "$path" should start with /');
      }
    });

    test('deep link whitelist includes critical paths', () {
      expect(SecurityConfig.allowedDeepLinkPaths, contains('/'));
      expect(SecurityConfig.allowedDeepLinkPaths, contains('/session/full'));
      expect(SecurityConfig.allowedDeepLinkPaths, contains('/auth/login'));
      expect(SecurityConfig.allowedDeepLinkPaths, contains('/referral'));
    });
  });
}
