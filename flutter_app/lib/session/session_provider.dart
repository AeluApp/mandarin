import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_response.dart';
import '../api/ws_client.dart';
import '../core/error_handler.dart';
import '../session/drill_cache.dart';

/// Drill input mode determined by the incoming WS message.
enum DrillInputMode {
  text,
  multipleChoice,
  audio,
  recording,
  action,
  toneMarking,
}

/// Session state managed by the provider.
class SessionState {
  final WsConnectionState connectionState;
  final Map<String, dynamic>? currentPrompt;
  final DrillInputMode inputMode;
  final int itemsCompleted;
  final int totalItems;
  final String? feedback;
  final bool feedbackCorrect;
  final bool showingFeedback;
  final String? hint;
  final String? resumeToken;
  final int sessionStartMs;
  final bool usingCache; // true when showing cached items before WS connects

  const SessionState({
    this.connectionState = WsConnectionState.connecting,
    this.currentPrompt,
    this.inputMode = DrillInputMode.text,
    this.itemsCompleted = 0,
    this.totalItems = 0,
    this.feedback,
    this.feedbackCorrect = false,
    this.showingFeedback = false,
    this.hint,
    this.resumeToken,
    this.sessionStartMs = 0,
    this.usingCache = false,
  });

  SessionState copyWith({
    WsConnectionState? connectionState,
    Map<String, dynamic>? currentPrompt,
    DrillInputMode? inputMode,
    int? itemsCompleted,
    int? totalItems,
    String? feedback,
    bool? feedbackCorrect,
    bool? showingFeedback,
    String? hint,
    String? resumeToken,
    int? sessionStartMs,
    bool? usingCache,
  }) {
    return SessionState(
      connectionState: connectionState ?? this.connectionState,
      currentPrompt: currentPrompt ?? this.currentPrompt,
      inputMode: inputMode ?? this.inputMode,
      itemsCompleted: itemsCompleted ?? this.itemsCompleted,
      totalItems: totalItems ?? this.totalItems,
      feedback: feedback ?? this.feedback,
      feedbackCorrect: feedbackCorrect ?? this.feedbackCorrect,
      showingFeedback: showingFeedback ?? this.showingFeedback,
      hint: hint,
      resumeToken: resumeToken ?? this.resumeToken,
      sessionStartMs: sessionStartMs ?? this.sessionStartMs,
      usingCache: usingCache ?? this.usingCache,
    );
  }

  // Clean prompt transition (clear feedback/hint when new prompt arrives).
  SessionState withNewPrompt(Map<String, dynamic> msg, DrillInputMode mode) {
    return SessionState(
      connectionState: connectionState,
      currentPrompt: msg,
      inputMode: mode,
      itemsCompleted: itemsCompleted,
      totalItems: totalItems,
      feedback: null,
      feedbackCorrect: false,
      showingFeedback: false,
      hint: null,
      resumeToken: resumeToken,
      sessionStartMs: sessionStartMs,
      usingCache: false,
    );
  }

  String get drillType {
    final v = currentPrompt?['drill_type'];
    return v is String ? v : '';
  }

  String get hanzi {
    final v = currentPrompt?['hanzi'];
    return v is String ? v : '';
  }

  String get pinyin {
    final v = currentPrompt?['pinyin'];
    return v is String ? v : '';
  }

  String get english {
    final v = currentPrompt?['english'];
    return v is String ? v : '';
  }

  String get promptText {
    final v = currentPrompt?['prompt_text'];
    return v is String ? v : '';
  }
  List<dynamic> get options =>
      (currentPrompt?['options'] as List<dynamic>?) ?? [];
}

class SessionNotifier extends StateNotifier<SessionState> {
  final WsClient _ws = WsClient();
  final DrillCache? _cache;
  StreamSubscription? _messageSub;
  StreamSubscription? _stateSub;

  SessionNotifier({DrillCache? cache})
      : _cache = cache,
        super(const SessionState());

  WsClient get ws => _ws;

  /// Start session with instant-start: show cached drill while WS connects.
  void start(String sessionType, String? accessToken) {
    if (accessToken != null) {
      _ws.setAccessToken(accessToken);
    }

    state = state.copyWith(
      sessionStartMs: DateTime.now().millisecondsSinceEpoch,
    );

    // Try cache-first for instant display.
    _tryCacheStart(sessionType);

    // Connect WS in parallel.
    _stateSub = _ws.connectionState.listen((connState) {
      state = state.copyWith(connectionState: connState);
    });

    _messageSub = _ws.messages.listen(_handleMessage);
    _ws.connect('/session/$sessionType');
  }

  /// Show cached first item immediately while WS connects.
  Future<void> _tryCacheStart(String sessionType) async {
    if (_cache == null) return;

    final age = await _cache.cacheAge(sessionType);
    // Only use cache if fresh (< 2 hours old).
    if (age == null || age.inHours >= 2) return;

    final cached = await _cache.getCached(sessionType);
    if (cached.isEmpty) return;

    // Show first cached item as a preview.
    final first = cached.first;
    state = state.copyWith(
      currentPrompt: first,
      inputMode: _parseInputMode(first),
      totalItems: cached.length,
      usingCache: true,
    );
  }

  void _handleMessage(Map<String, dynamic> msg) {
    final type = msg.str('type');

    // Validate required 'type' field.
    if (type.isEmpty) return;

    switch (type) {
      case 'session_init':
        state = state.copyWith(
          totalItems: msg.integer('total_items'),
          itemsCompleted: 0,
          resumeToken: msg.strOrNull('resume_token'),
          usingCache: false,
        );
        break;

      case 'show':
      case 'prompt':
        state = state.withNewPrompt(msg, _parseInputMode(msg));
        break;

      case 'feedback':
        final correct = msg['correct'] == true;
        state = state.copyWith(
          feedback: msg.strOrNull('message'),
          feedbackCorrect: correct,
          showingFeedback: true,
          itemsCompleted:
              correct ? state.itemsCompleted + 1 : state.itemsCompleted,
        );
        break;

      case 'hint':
        state = state.copyWith(hint: msg.strOrNull('text'));
        break;

      case 'record_request':
        state = state.copyWith(inputMode: DrillInputMode.recording);
        break;

      case 'done':
        // Handled by the screen via message stream.
        break;
    }
  }

  DrillInputMode _parseInputMode(Map<String, dynamic> msg) {
    final options = msg['options'];
    if (options is List && options.isNotEmpty) {
      return DrillInputMode.multipleChoice;
    }

    final drillType = msg.str('drill_type');
    if (drillType.contains('speaking') ||
        drillType.contains('pronunciation')) {
      return DrillInputMode.recording;
    }
    if (drillType.contains('tone')) return DrillInputMode.toneMarking;
    if (drillType == 'action') return DrillInputMode.action;

    return DrillInputMode.text;
  }

  void submitAnswer(String answer) => _ws.sendAnswer(answer);
  void submitChoice(int index) => _ws.sendChoice(index);
  void sendSkip() => _ws.sendSkip();
  void requestHint() => _ws.sendHint();
  void sendAudio(String base64) => _ws.sendAudio(base64);

  Future<void> disconnect() async => _ws.disconnect();

  @override
  void dispose() {
    _messageSub?.cancel();
    _stateSub?.cancel();
    _ws.dispose();
    super.dispose();
  }
}

final sessionProvider =
    StateNotifierProvider.autoDispose<SessionNotifier, SessionState>((ref) {
  DrillCache? cache;
  try {
    cache = ref.read(drillCacheProvider);
  } catch (e, st) {
    ErrorHandler.log('Session read drill cache', e, st);
    cache = null;
  }
  final notifier = SessionNotifier(cache: cache);
  ref.onDispose(() => notifier.dispose());
  return notifier;
});
