import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';

import '../../theme/aelu_colors.dart';

/// Slim offline banner — slides down when disconnected, slides up on reconnect.
class OfflineBanner extends StatefulWidget {
  const OfflineBanner({super.key});

  @override
  State<OfflineBanner> createState() => _OfflineBannerState();
}

class _OfflineBannerState extends State<OfflineBanner> {
  bool _offline = false;
  StreamSubscription<List<ConnectivityResult>>? _sub;

  @override
  void initState() {
    super.initState();
    _sub = Connectivity().onConnectivityChanged.listen((results) {
      final isOffline = results.every((r) => r == ConnectivityResult.none);
      if (mounted && isOffline != _offline) {
        setState(() => _offline = isOffline);
      }
    });
    // Check initial state.
    Connectivity().checkConnectivity().then((results) {
      if (mounted) {
        setState(() =>
            _offline = results.every((r) => r == ConnectivityResult.none));
      }
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return AnimatedSlide(
      offset: _offline ? Offset.zero : const Offset(0, -1),
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOutCubic,
      child: AnimatedOpacity(
        opacity: _offline ? 1.0 : 0.0,
        duration: const Duration(milliseconds: 200),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          color: isDark ? AeluColors.surfaceAltDark : AeluColors.surfaceAltLight,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.cloud_off_outlined,
                size: 14,
                color: isDark ? AeluColors.textDimDark : AeluColors.textDimLight,
              ),
              const SizedBox(width: 8),
              Text(
                "You're offline — your progress will sync when you reconnect",
                style: TextStyle(
                  fontFamily: 'SourceSerif4',
                  fontSize: 12,
                  color: isDark ? AeluColors.textDimDark : AeluColors.textDimLight,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
