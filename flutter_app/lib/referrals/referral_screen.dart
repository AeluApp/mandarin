import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/animations/drift_up.dart';
import '../theme/aelu_spacing.dart';
import '../core/error_handler.dart';
import '../core/animations/content_switcher.dart';
import '../core/animations/pressable_scale.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';

class ReferralScreen extends ConsumerStatefulWidget {
  const ReferralScreen({super.key});

  @override
  ConsumerState<ReferralScreen> createState() => _ReferralScreenState();
}

class _ReferralScreenState extends ConsumerState<ReferralScreen> {
  String? _referralLink;
  int _referralCount = 0;
  bool _loading = true;
  bool _loadError = false;

  @override
  void initState() {
    super.initState();
    _loadReferralInfo();
  }

  Future<void> _loadReferralInfo() async {
    try {
      final response = await ref.read(apiClientProvider).get('/api/account/referral');
      final data = SafeMap.from(response.data);
      if (data == null) return;
      setState(() {
        _referralLink = data.strOrNull('link');
        _referralCount = data.integer('count');
        _loading = false;
        _loadError = false;
      });
    } catch (e, st) {
      ErrorHandler.log('Referral load info', e, st);
      setState(() {
        _loading = false;
        _loadError = true;
      });
      if (mounted) {
        AeluSnackbar.show(context, 'Couldn\'t load referral info.', type: SnackbarType.error);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Invite Friends')),
      body: ContentSwitcher(
        child: _loading
          ? const Padding(
              key: ValueKey('loading'),
              padding: EdgeInsets.all(24),
              child: Column(
                children: [
                  SizedBox(height: 32),
                  SkeletonLine(width: 64, height: 64),
                  SizedBox(height: 16),
                  SkeletonLine(width: 160, height: 24),
                  SizedBox(height: 8),
                  SkeletonLine(width: 240, height: 14),
                  SizedBox(height: 32),
                  SkeletonLine(height: 48),
                  SizedBox(height: 24),
                  SkeletonPanel(height: 80),
                ],
              ),
            )
          : _loadError
              ? Center(
                  key: const ValueKey('error'),
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.error_outline, size: 56, color: AeluColors.mutedOf(context)),
                        const SizedBox(height: 16),
                        Text('Couldn\'t load referral info', style: theme.textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Text(
                          'Check your connection and try again.',
                          style: theme.textTheme.bodySmall,
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 20),
                        OutlinedButton(onPressed: _loadReferralInfo, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    children: [
                      DriftUp(
                        child: Icon(Icons.group_add_outlined, size: 64, color: AeluColors.accentOf(context)),
                      ),
                      const SizedBox(height: 16),
                      DriftUp(
                        delay: const Duration(milliseconds: 50),
                        child: Text('Give a month, get a month', style: theme.textTheme.displayMedium, textAlign: TextAlign.center),
                      ),
                      const SizedBox(height: 8),
                      DriftUp(
                        delay: const Duration(milliseconds: 100),
                        child: Text(
                          'When a friend signs up with your link, you both get a free month of Aelu Pro.',
                          style: theme.textTheme.bodyMedium,
                          textAlign: TextAlign.center,
                        ),
                      ),
                      const SizedBox(height: 28),
                      if (_referralLink != null) ...[
                        DriftUp(
                          delay: const Duration(milliseconds: 150),
                          child: Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: theme.brightness == Brightness.dark
                                  ? AeluColors.dividerDark
                                  : AeluColors.divider,
                            ),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  _referralLink!,
                                  style: theme.textTheme.bodyMedium,
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                              PressableScale(
                                onTap: () {
                                  ref.read(soundProvider).play(SoundEvent.navigate);
                                  Clipboard.setData(ClipboardData(text: _referralLink!));
                                  AeluSnackbar.show(context, 'Link copied!', type: SnackbarType.success);
                                },
                                child: const Padding(
                                  padding: EdgeInsets.all(10),
                                  child: Icon(Icons.content_copy_outlined, size: 24),
                                ),
                              ),
                            ],
                          ),
                        ),
                        ),
                        const SizedBox(height: 16),
                        DriftUp(
                          delay: const Duration(milliseconds: 175),
                          child: SizedBox(
                            width: double.infinity,
                            child: PressableScale(
                              onTap: () {
                                HapticFeedback.selectionClick();
                                Share.share(
                                  'I\'m learning Mandarin with Aelu — join me and we both get a free month: $_referralLink',
                                );
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 14),
                                decoration: BoxDecoration(
                                  color: AeluColors.accentOf(context),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    const Icon(Icons.share_outlined, size: 18, color: AeluColors.onAccent),
                                    const SizedBox(width: 8),
                                    Text(
                                      'Share with friends',
                                      style: theme.textTheme.titleMedium?.copyWith(color: AeluColors.onAccent),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 24),
                      ],
                      DriftUp(
                        delay: const Duration(milliseconds: 200),
                        child: Card(
                        child: Padding(
                          padding: const EdgeInsets.all(20),
                          child: Column(
                            children: [
                              Text(
                                '$_referralCount',
                                style: theme.textTheme.displayLarge?.copyWith(
                                  color: AeluColors.accentOf(context),
                                ),
                              ),
                              Text(
                                _referralCount == 1 ? 'friend invited' : 'friends invited',
                                style: theme.textTheme.bodySmall,
                              ),
                              if (_referralCount > 0 && _referralCount < 5) ...[
                                const SizedBox(height: 8),
                                Text(
                                  '${5 - _referralCount} more for a bonus month',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: AeluColors.accentOf(context),
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                      ),
                    ],
                  ),
                ),
      ),
    );
  }
}
