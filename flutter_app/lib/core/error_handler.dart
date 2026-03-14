import 'dart:collection';
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:dio/dio.dart';

import 'security/security_config.dart';

/// Global error handling — ring buffer + batch reporting.
///
/// Security controls:
/// - NIST SI-11 (Error Handling): Stack traces truncated, local paths stripped.
/// - ISO 27001 A.12.4.1 (Event logging): Structured error records.
/// - OWASP M9 (Reverse Engineering): No internal paths or secrets in reports.
class ErrorHandler {
  static final _errors = Queue<_ErrorEntry>();
  static const _maxErrors = 200;
  static Dio? _dio;
  static Timer? _flushTimer;

  static void init(String apiUrl) {
    _dio = Dio(BaseOptions(
      baseUrl: apiUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
    ));
    _flushTimer = Timer.periodic(const Duration(seconds: 60), (_) => _flush());
  }

  static void onFlutterError(FlutterErrorDetails details) {
    _record(details.exception.toString(), details.stack?.toString());
  }

  static bool onPlatformError(Object error, StackTrace stack) {
    _record(error.toString(), stack.toString());
    return true;
  }

  /// Log a non-fatal error with context for debugging.
  ///
  /// Call this instead of silently swallowing exceptions in catch blocks.
  static void log(String context, [Object? error, StackTrace? stack]) {
    final message = error != null ? '$context: $error' : context;
    _record(message, stack?.toString());
  }

  static void _record(String message, String? stack) {
    // SECURITY: Scrub PII from error messages.
    final safeMessage = PiiScrubber.scrub(message);

    // SECURITY: Truncate and sanitize stack traces — strip local paths,
    // limit to 5 frames (NIST SI-11).
    final safeStack = PiiScrubber.sanitizeStackTrace(stack, maxFrames: 5);

    _errors.addLast(_ErrorEntry(
      message: safeMessage,
      stack: safeStack,
      timestamp: DateTime.now().toUtc().toIso8601String(),
    ));
    while (_errors.length > _maxErrors) {
      _errors.removeFirst();
    }
  }

  static Future<void> _flush() async {
    if (_dio == null || _errors.isEmpty) return;
    final batch = _errors.toList();
    _errors.clear();
    try {
      await _dio!.post('/api/error-report', data: {
        'platform': 'flutter',
        'errors': batch.map((e) => {
          'message': e.message,
          'stack': e.stack,
          'timestamp': e.timestamp,
        }).toList(),
      });
    } catch (_) {
      for (final err in batch) {
        _errors.addLast(err);
        if (_errors.length >= _maxErrors) break;
      }
    }
  }

  static void dispose() {
    _flushTimer?.cancel();
  }
}

class _ErrorEntry {
  final String message;
  final String? stack;
  final String timestamp;

  const _ErrorEntry({required this.message, this.stack, required this.timestamp});
}
