import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/error_handler.dart';

// ── Data models ──

class GrammarPoint {
  final int id;
  final String name;
  final String nameZh;
  final String category;
  final int hskLevel;
  final String description;
  final List<GrammarExample> examples;
  final List<GrammarVocab> relatedVocab;
  final bool studied;
  final String? studiedAt;

  const GrammarPoint({
    required this.id,
    required this.name,
    required this.nameZh,
    required this.category,
    required this.hskLevel,
    required this.description,
    required this.examples,
    required this.relatedVocab,
    required this.studied,
    this.studiedAt,
  });

  factory GrammarPoint.fromJson(Map<String, dynamic> json) {
    final examples = json.list('examples')
        .whereType<Map<String, dynamic>>()
        .map(GrammarExample.fromJson)
        .toList();
    final vocab = json.list('related_vocab')
        .whereType<Map<String, dynamic>>()
        .map(GrammarVocab.fromJson)
        .toList();
    return GrammarPoint(
      id: json.integer('id'),
      name: json.str('name'),
      nameZh: json.str('name_zh'),
      category: json.str('category'),
      hskLevel: json.integer('hsk_level', 1),
      description: json.str('description'),
      examples: examples,
      relatedVocab: vocab,
      studied: json.boolean('studied'),
      studiedAt: json.strOrNull('studied_at'),
    );
  }
}

class GrammarExample {
  final String chinese;
  final String pinyin;
  final String english;

  const GrammarExample({
    required this.chinese,
    required this.pinyin,
    required this.english,
  });

  factory GrammarExample.fromJson(Map<String, dynamic> json) {
    return GrammarExample(
      chinese: json.str('chinese'),
      pinyin: json.str('pinyin'),
      english: json.str('english'),
    );
  }
}

class GrammarVocab {
  final String hanzi;
  final String pinyin;
  final String english;
  final String stage;

  const GrammarVocab({
    required this.hanzi,
    required this.pinyin,
    required this.english,
    required this.stage,
  });

  factory GrammarVocab.fromJson(Map<String, dynamic> json) {
    return GrammarVocab(
      hanzi: json.str('hanzi'),
      pinyin: json.str('pinyin'),
      english: json.str('english'),
      stage: json.str('stage'),
    );
  }
}

class GrammarMastery {
  final int studied;
  final int total;

  const GrammarMastery({required this.studied, required this.total});

  double get pct => total > 0 ? studied / total * 100 : 0;
}

class GrammarState {
  final List<GrammarPoint> points;
  final GrammarPoint? selectedPoint;
  final Map<int, GrammarMastery> masteryByLevel;
  final bool loading;
  final String? error;

  const GrammarState({
    this.points = const [],
    this.selectedPoint,
    this.masteryByLevel = const {},
    this.loading = false,
    this.error,
  });

  GrammarState copyWith({
    List<GrammarPoint>? points,
    GrammarPoint? selectedPoint,
    bool clearSelectedPoint = false,
    Map<int, GrammarMastery>? masteryByLevel,
    bool? loading,
    String? error,
    bool clearError = false,
  }) {
    return GrammarState(
      points: points ?? this.points,
      selectedPoint: clearSelectedPoint ? null : (selectedPoint ?? this.selectedPoint),
      masteryByLevel: masteryByLevel ?? this.masteryByLevel,
      loading: loading ?? this.loading,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

class GrammarNotifier extends StateNotifier<GrammarState> {
  final ApiClient _api;

  GrammarNotifier(this._api) : super(const GrammarState());

  /// Fetch grammar points for a given HSK level.
  Future<void> loadLevel(int hskLevel) async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final response = await _api.get('/api/grammar/lesson/$hskLevel');
      final data = response.data;
      if (data is! Map<String, dynamic>) {
        state = state.copyWith(
          loading: false,
          error: 'Couldn\'t load grammar points.',
        );
        return;
      }
      final rawPoints = data.list('points');
      final points = rawPoints
          .whereType<Map<String, dynamic>>()
          .map(GrammarPoint.fromJson)
          .toList();
      state = state.copyWith(points: points, loading: false);
    } catch (e, st) {
      ErrorHandler.log('Grammar load level $hskLevel', e, st);
      state = state.copyWith(
        loading: false,
        error: 'Couldn\'t load grammar points.',
      );
    }
  }

  /// Fetch a single grammar point by ID.
  Future<void> loadPoint(int id) async {
    state = state.copyWith(loading: true, clearError: true, clearSelectedPoint: true);
    try {
      final response = await _api.get('/api/grammar/point/$id');
      final data = SafeMap.from(response.data);
      if (data == null) {
        state = state.copyWith(
          loading: false,
          error: 'Couldn\'t load this grammar point.',
        );
        return;
      }
      final point = GrammarPoint.fromJson(data);
      state = state.copyWith(selectedPoint: point, loading: false);
    } catch (e, st) {
      ErrorHandler.log('Grammar load point $id', e, st);
      state = state.copyWith(
        loading: false,
        error: 'Couldn\'t load this grammar point.',
      );
    }
  }

  /// Mark a grammar point as studied.
  Future<bool> markStudied(int grammarPointId) async {
    try {
      await _api.post('/api/grammar/progress', data: {
        'grammar_point_id': grammarPointId,
      });

      // Update the selected point if it matches.
      if (state.selectedPoint?.id == grammarPointId) {
        final now = DateTime.now().toIso8601String();
        state = state.copyWith(
          selectedPoint: GrammarPoint(
            id: state.selectedPoint!.id,
            name: state.selectedPoint!.name,
            nameZh: state.selectedPoint!.nameZh,
            category: state.selectedPoint!.category,
            hskLevel: state.selectedPoint!.hskLevel,
            description: state.selectedPoint!.description,
            examples: state.selectedPoint!.examples,
            relatedVocab: state.selectedPoint!.relatedVocab,
            studied: true,
            studiedAt: now,
          ),
        );
      }

      // Update the point in the list.
      final updatedPoints = state.points.map((p) {
        if (p.id == grammarPointId) {
          return GrammarPoint(
            id: p.id,
            name: p.name,
            nameZh: p.nameZh,
            category: p.category,
            hskLevel: p.hskLevel,
            description: p.description,
            examples: p.examples,
            relatedVocab: p.relatedVocab,
            studied: true,
            studiedAt: DateTime.now().toIso8601String(),
          );
        }
        return p;
      }).toList();
      state = state.copyWith(points: updatedPoints);

      return true;
    } catch (e, st) {
      ErrorHandler.log('Grammar mark studied $grammarPointId', e, st);
      return false;
    }
  }

  /// Fetch mastery summary across all levels.
  Future<void> loadMastery() async {
    try {
      final response = await _api.get('/api/grammar/mastery');
      final data = response.data;
      if (data is! Map<String, dynamic>) return;

      final rawLevels = data.nested('levels');
      final mastery = <int, GrammarMastery>{};
      for (final entry in rawLevels.entries) {
        final level = int.tryParse(entry.key);
        if (level != null && entry.value is Map<String, dynamic>) {
          final m = entry.value as Map<String, dynamic>;
          mastery[level] = GrammarMastery(
            studied: m.integer('studied'),
            total: m.integer('total'),
          );
        }
      }
      state = state.copyWith(masteryByLevel: mastery);
    } catch (e, st) {
      ErrorHandler.log('Grammar load mastery', e, st);
    }
  }
}

final grammarProvider =
    StateNotifierProvider.autoDispose<GrammarNotifier, GrammarState>((ref) {
  final api = ref.watch(apiClientProvider);
  return GrammarNotifier(api);
});
