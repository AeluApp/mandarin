import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../api/api_client.dart';

/// Cached experiment variant assignments for the current user.
/// Fetches from /api/experiments/my-variants and caches locally.
class ExperimentState {
  final Map<String, String> variants; // experiment_name -> variant
  final bool loading;
  final String? error;

  const ExperimentState({
    this.variants = const {},
    this.loading = false,
    this.error,
  });

  ExperimentState copyWith({
    Map<String, String>? variants,
    bool? loading,
    String? error,
  }) {
    return ExperimentState(
      variants: variants ?? this.variants,
      loading: loading ?? this.loading,
      error: error,
    );
  }

  String? getVariant(String experimentName) => variants[experimentName];

  bool isInVariant(String experimentName, String variant) =>
      variants[experimentName] == variant;
}

class ExperimentNotifier extends StateNotifier<ExperimentState> {
  final ApiClient _api;

  ExperimentNotifier(this._api)
      : super(const ExperimentState(loading: true)) {
    _loadCached();
  }

  static const _cacheKey = 'experiment_variants';

  /// Load cached variants from SharedPreferences for offline support.
  Future<void> _loadCached() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final cached = prefs.getString(_cacheKey);
      if (cached != null) {
        final map = Map<String, String>.from(jsonDecode(cached) as Map);
        state = ExperimentState(variants: map);
      } else {
        state = const ExperimentState();
      }
    } catch (_) {
      state = const ExperimentState();
    }
  }

  /// Fetch fresh variant assignments from the server and cache locally.
  Future<void> fetchVariants() async {
    try {
      state = state.copyWith(loading: true);
      final resp = await _api.get('/api/experiments/my-variants');
      if (resp.statusCode == 200) {
        final data = resp.data;
        if (data is Map<String, dynamic>) {
          final raw = data['variants'];
          final variants = raw is Map
              ? Map<String, String>.from(raw)
              : <String, String>{};
          state = ExperimentState(variants: variants);
          // Cache locally for offline access.
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString(_cacheKey, jsonEncode(variants));
        }
      }
    } catch (e) {
      state = ExperimentState(
        variants: state.variants, // keep cached
        error: e.toString(),
      );
    }
  }

  /// Log that the user was exposed to an experiment variant.
  Future<void> logExposure(
    String experimentName, {
    String? context,
  }) async {
    try {
      await _api.post('/api/experiments/expose', data: {
        'experiment_name': experimentName,
        'context': context ?? 'flutter_app',
      });
    } catch (_) {
      // Fire-and-forget: exposure logging should never block the UI.
    }
  }
}

final experimentProvider =
    StateNotifierProvider<ExperimentNotifier, ExperimentState>((ref) {
  final api = ref.watch(apiClientProvider);
  return ExperimentNotifier(api);
});
