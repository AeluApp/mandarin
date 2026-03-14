/// Type-safe API response parsing helpers.
///
/// Eliminates unsafe `as` casts on API response data by providing
/// null-safe extraction methods with sensible defaults.
extension SafeMap on Map<String, dynamic> {
  /// Get a string value, or empty string if missing/wrong type.
  String str(String key) {
    final v = this[key];
    return v is String ? v : '';
  }

  /// Get a nullable string value.
  String? strOrNull(String key) {
    final v = this[key];
    return v is String ? v : null;
  }

  /// Get an int value, or default if missing/wrong type.
  int integer(String key, [int defaultValue = 0]) {
    final v = this[key];
    if (v is int) return v;
    if (v is num) return v.toInt();
    return defaultValue;
  }

  /// Get a bool value, or default if missing/wrong type.
  bool boolean(String key, [bool defaultValue = false]) {
    final v = this[key];
    return v is bool ? v : defaultValue;
  }

  /// Get a nested map, or empty map if missing/wrong type.
  Map<String, dynamic> nested(String key) {
    final v = this[key];
    return v is Map<String, dynamic> ? v : <String, dynamic>{};
  }

  /// Get a nullable nested map.
  Map<String, dynamic>? nestedOrNull(String key) {
    final v = this[key];
    return v is Map<String, dynamic> ? v : null;
  }

  /// Get a list, or empty list if missing/wrong type.
  List<dynamic> list(String key) {
    final v = this[key];
    return v is List ? v : <dynamic>[];
  }

  /// Safely cast response.data to Map, returning null if invalid.
  static Map<String, dynamic>? from(dynamic data) {
    return data is Map<String, dynamic> ? data : null;
  }
}
