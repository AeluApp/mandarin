import 'dart:async';

import 'package:flutter/material.dart';

/// Elapsed session timer (hidden for first 3 sessions).
class SessionTimer extends StatefulWidget {
  final int startMs;

  const SessionTimer({super.key, required this.startMs});

  @override
  State<SessionTimer> createState() => _SessionTimerState();
}

class _SessionTimerState extends State<SessionTimer> {
  Timer? _timer;
  Duration _elapsed = Duration.zero;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() {
        _elapsed = Duration(
          milliseconds: DateTime.now().millisecondsSinceEpoch - widget.startMs,
        );
      });
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final minutes = _elapsed.inMinutes;
    final seconds = _elapsed.inSeconds % 60;
    return Semantics(
      label: '$minutes minutes $seconds seconds elapsed',
      child: Text(
        '${minutes.toString().padLeft(2, '0')}:${seconds.toString().padLeft(2, '0')}',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );
  }
}
