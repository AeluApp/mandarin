import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/ws_client.dart';
import '../auth/auth_provider.dart';
import '../core/animations/content_switcher.dart';
import '../theme/aelu_spacing.dart';
import '../core/animations/ink_spread.dart';
import '../core/animations/pressable_scale.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/gesture_tutorial.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';
import 'session_provider.dart';
import 'widgets/audio_recorder.dart';
import 'widgets/drill_input.dart';
import 'widgets/drill_view.dart';
import 'widgets/feedback_bar.dart';
import 'widgets/hint_overlay.dart';
import 'widgets/mc_options.dart';
import 'widgets/quit_dialog.dart';
import 'widgets/tone_marker.dart';

class SessionScreen extends ConsumerStatefulWidget {
  final String sessionType;
  const SessionScreen({super.key, required this.sessionType});

  @override
  ConsumerState<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends ConsumerState<SessionScreen> {
  final _answerController = TextEditingController();
  final _focusNode = FocusNode();
  StreamSubscription? _doneSub;
  bool _showGestureTutorial = false;

  @override
  void initState() {
    super.initState();

    // Immersive mode — hide status bar during session.
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

    final auth = ref.read(authProvider);
    final notifier = ref.read(sessionProvider.notifier);
    notifier.start(widget.sessionType, auth.accessToken);

    ref.read(soundProvider).play(SoundEvent.sessionStart);

    _doneSub = notifier.ws.messages.listen((msg) {
      if (msg['type'] == 'done' && mounted) {
        final raw = msg['results'];
        final results = raw is Map<String, dynamic> ? raw : <String, dynamic>{};
        context.go('/complete', extra: results);
      }
    });

    // Check if gesture tutorial should be shown.
    GestureTutorial.hasBeenShown().then((shown) {
      if (!shown && mounted) {
        setState(() => _showGestureTutorial = true);
      }
    });
  }

  @override
  void dispose() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    _doneSub?.cancel();
    _answerController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _submitAnswer() {
    final answer = _answerController.text.trim();
    if (answer.isEmpty) return;
    ref.read(sessionProvider.notifier).submitAnswer(answer);
    _answerController.clear();
  }

  void _selectChoice(int index) {
    ref.read(sessionProvider.notifier).submitChoice(index);
  }

  void _submitTone(String tone) {
    ref.read(sessionProvider.notifier).submitAnswer(tone);
  }

  void _onAudioRecorded(String base64) {
    ref.read(sessionProvider.notifier).sendAudio(base64);
  }

  void _requestHint() {
    unawaited(HapticFeedback.selectionClick());
    ref.read(soundProvider).play(SoundEvent.hintReveal);
    ref.read(sessionProvider.notifier).requestHint();
  }

  void _skip() {
    ref.read(soundProvider).play(SoundEvent.navigate);
    ref.read(sessionProvider.notifier).sendSkip();
  }

  Future<void> _quit() async {
    unawaited(HapticFeedback.selectionClick());
    final session = ref.read(sessionProvider);
    final confirmed = await QuitDialog.show(
      context,
      completed: session.itemsCompleted,
      total: session.totalItems,
    );
    if (confirmed && mounted) {
      unawaited(ref.read(soundProvider).play(SoundEvent.transitionOut));
      await ref.read(sessionProvider.notifier).disconnect();
      if (mounted) context.go('/');
    }
  }

  KeyEventResult _handleKeyEvent(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    final session = ref.read(sessionProvider);

    switch (event.logicalKey) {
      case LogicalKeyboardKey.keyQ:
        _quit();
        return KeyEventResult.handled;
      case LogicalKeyboardKey.question:
        _requestHint();
        return KeyEventResult.handled;
      case LogicalKeyboardKey.keyN:
        _skip();
        return KeyEventResult.handled;
      case LogicalKeyboardKey.digit1:
      case LogicalKeyboardKey.digit2:
      case LogicalKeyboardKey.digit3:
      case LogicalKeyboardKey.digit4:
        if (session.inputMode == DrillInputMode.multipleChoice) {
          final digit =
              event.logicalKey.keyId - LogicalKeyboardKey.digit1.keyId;
          if (digit < session.options.length) {
            _selectChoice(digit);
            return KeyEventResult.handled;
          }
        }
        return KeyEventResult.ignored;
      default:
        return KeyEventResult.ignored;
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final sound = ref.read(soundProvider);

    // Play sound + haptic on feedback.
    ref.listen<SessionState>(sessionProvider, (prev, next) {
      if (next.showingFeedback && !(prev?.showingFeedback ?? false)) {
        sound.play(
            next.feedbackCorrect ? SoundEvent.correct : SoundEvent.wrong);
      }
    });

    return Focus(
      focusNode: _focusNode,
      onKeyEvent: _handleKeyEvent,
      autofocus: true,
      child: GestureDetector(
        onPanStart: (_) {},
        onPanEnd: (d) {
          final dx = d.velocity.pixelsPerSecond.dx;
          final dy = d.velocity.pixelsPerSecond.dy;

          if (dx > 400 && dy.abs() < 300) {
            _submitAnswer(); // swipe right
          } else if (dx < -400 && dy.abs() < 300) {
            _skip(); // swipe left
          } else if (dy > 400 && dx.abs() < 300) {
            _requestHint(); // pull down
          }
        },
        child: Scaffold(
          backgroundColor: Theme.of(context).scaffoldBackgroundColor,
          body: Stack(
            children: [
              ContentSwitcher(child: _buildBody(session)),
              if (_showGestureTutorial)
                Positioned.fill(
                  child: GestureTutorial(
                    onDismiss: () => setState(() => _showGestureTutorial = false),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(SessionState session) {
    if (session.connectionState == WsConnectionState.connecting ||
        session.connectionState == WsConnectionState.reconnecting) {
      // If we have cached content, show it instead of skeleton.
      if (session.currentPrompt != null) {
        return _buildDrillView(session);
      }
      return const SessionSkeleton(key: ValueKey('skeleton'));
    }

    if (session.connectionState == WsConnectionState.failed) {
      return SafeArea(
        key: const ValueKey('failed'),
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.wifi_off_outlined,
                    size: 56, color: AeluColors.mutedOf(context)),
                const SizedBox(height: 16),
                Text('Connection lost',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                Text('Your progress has been saved',
                    style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 20),
                ElevatedButton(
                  onPressed: () {
                    final auth = ref.read(authProvider);
                    ref.read(sessionProvider.notifier).start(
                          widget.sessionType,
                          auth.accessToken,
                        );
                  },
                  child: const Text('Retry'),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: () => context.go('/'),
                  child: const Text('Return home'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    if (session.currentPrompt == null) {
      return const SessionSkeleton(key: ValueKey('waiting'));
    }

    return _buildDrillView(session);
  }

  Widget _buildDrillView(SessionState session) {
    final progress = session.totalItems > 0
        ? session.itemsCompleted / session.totalItems
        : 0.0;

    return SafeArea(
      child: Column(
        children: [
          // ── Minimal top bar ──
          Padding(
            padding:
                const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                PressableScale(
                  onTap: _quit,
                  child: Semantics(
                    button: true,
                    label: 'End session',
                    child: const Padding(
                      padding: EdgeInsets.all(10),
                      child: Icon(Icons.close_outlined, size: 24),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Semantics(
                    label:
                        '${session.itemsCompleted} of ${session.totalItems}',
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(2),
                      child: LinearProgressIndicator(
                        value: progress,
                        minHeight: 3,
                        backgroundColor:
                            Theme.of(context).dividerTheme.color,
                        valueColor: AlwaysStoppedAnimation(
                            AeluColors.secondaryOf(context)),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  '${session.itemsCompleted}/${session.totalItems}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),

          // ── Drill content ──
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: [
                  const Spacer(flex: 2),

                  InkSpread(
                    color: session.feedbackCorrect
                        ? AeluColors.correctOf(context)
                        : Colors.transparent,
                    trigger:
                        session.showingFeedback && session.feedbackCorrect,
                    child: DrillView(session: session),
                  ),

                  const Spacer(flex: 1),

                  // Hint
                  if (session.hint != null) ...[
                    HintOverlay(hint: session.hint!),
                    const SizedBox(height: 12),
                  ],

                  // Feedback
                  if (session.showingFeedback &&
                      session.feedback != null) ...[
                    FeedbackBar(
                      message: session.feedback!,
                      correct: session.feedbackCorrect,
                    ),
                    const SizedBox(height: 12),
                  ],

                  // Input area
                  _buildInput(session),

                  const SizedBox(height: 16),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInput(SessionState session) {
    switch (session.inputMode) {
      case DrillInputMode.multipleChoice:
        return McOptions(
          options: session.options,
          onSelect: _selectChoice,
        );
      case DrillInputMode.recording:
        return AudioRecorderWidget(onRecorded: _onAudioRecorded);
      case DrillInputMode.toneMarking:
        return ToneMarker(onSelect: _submitTone);
      case DrillInputMode.action:
        return PressableScale(
          onTap: () {
            HapticFeedback.selectionClick();
            ref.read(sessionProvider.notifier).submitAnswer('done');
          },
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
            decoration: BoxDecoration(
              color: AeluColors.accentOf(context),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              'Done',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(color: AeluColors.onAccent),
            ),
          ),
        );
      case DrillInputMode.text:
      case DrillInputMode.audio:
        return DrillInput(
          controller: _answerController,
          onSubmit: _submitAnswer,
        );
    }
  }
}
