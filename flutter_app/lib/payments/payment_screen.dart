import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_stripe/flutter_stripe.dart' hide Card;

import '../core/animations/content_switcher.dart';
import '../theme/aelu_spacing.dart';
import '../core/animations/drift_up.dart';
import '../core/animations/pressable_scale.dart';
import '../core/error_handler.dart';
import '../core/sound/aelu_sound.dart';
import '../core/sound/sound_events.dart';
import '../shared/widgets/aelu_snackbar.dart';
import '../shared/widgets/skeleton.dart';
import '../theme/aelu_colors.dart';
import 'payment_provider.dart';

class PaymentScreen extends ConsumerWidget {
  const PaymentScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final payment = ref.watch(paymentProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Subscription')),
      body: ContentSwitcher(
        child: payment.loading
          ? const Padding(
              key: ValueKey('loading'),
              padding: EdgeInsets.all(24),
              child: Column(
                children: [
                  SizedBox(height: 16),
                  SkeletonLine(width: 180, height: 28),
                  SizedBox(height: 24),
                  SkeletonPanel(height: 80),
                  SizedBox(height: 12),
                  SkeletonPanel(height: 80),
                ],
              ),
            )
          : SingleChildScrollView(
              key: const ValueKey('content'),
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  if (payment.isActive) ...[
                    DriftUp(child: _ActivePlanCard(payment: payment)),
                    const SizedBox(height: 24),
                    DriftUp(
                      delay: const Duration(milliseconds: 100),
                      child: Builder(builder: (ctx) {
                        final errorColor = Theme.of(ctx).colorScheme.error;
                        return OutlinedButton(
                          onPressed: () => _confirmCancel(context, ref),
                          style: OutlinedButton.styleFrom(
                            side: BorderSide(color: errorColor),
                          ),
                          child: Text(
                            'Cancel Subscription',
                            style: TextStyle(color: errorColor),
                          ),
                        );
                      }),
                    ),
                  ] else ...[
                    DriftUp(
                      child: Text('Unlock Aelu Pro', style: theme.textTheme.displayMedium),
                    ),
                    const SizedBox(height: 8),
                    DriftUp(
                      delay: const Duration(milliseconds: 50),
                      child: Text(
                        'Everything you need to reach fluency.',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: AeluColors.mutedOf(context),
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                    const SizedBox(height: 24),
                    DriftUp(
                      delay: const Duration(milliseconds: 100),
                      child: _FeatureList(),
                    ),
                    const SizedBox(height: 28),
                    DriftUp(
                      delay: const Duration(milliseconds: 150),
                      child: _PlanCard(
                        title: 'Annual',
                        price: '\$149/yr',
                        perMonth: '\$12.42/mo',
                        subtitle: 'Save 17%',
                        badge: 'Best value',
                        plan: 'annual',
                        onSelect: () => _startCheckout(context, ref, 'annual'),
                      ),
                    ),
                    const SizedBox(height: 12),
                    DriftUp(
                      delay: const Duration(milliseconds: 200),
                      child: _PlanCard(
                        title: 'Monthly',
                        price: '\$14.99/mo',
                        plan: 'monthly',
                        onSelect: () => _startCheckout(context, ref, 'monthly'),
                      ),
                    ),
                    const SizedBox(height: 16),
                    DriftUp(
                      delay: const Duration(milliseconds: 250),
                      child: Text(
                        'Cancel anytime. No commitments.',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: AeluColors.mutedOf(context),
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ],
                ],
              ),
            ),
      ),
    );
  }

  Future<void> _startCheckout(BuildContext context, WidgetRef ref, String plan) async {
    unawaited(ref.read(soundProvider).play(SoundEvent.navigate));
    final notifier = ref.read(paymentProvider.notifier);
    final secret = await notifier.createCheckoutSession(plan);
    if (secret == null) {
      if (context.mounted) {
        AeluSnackbar.show(context, 'Couldn\'t start checkout. Try again.', type: SnackbarType.error);
      }
      return;
    }

    // Present Stripe Payment Sheet.
    try {
      await Stripe.instance.initPaymentSheet(
        paymentSheetParameters: SetupPaymentSheetParameters(
          paymentIntentClientSecret: secret,
          merchantDisplayName: 'Aelu',
        ),
      );
      await Stripe.instance.presentPaymentSheet();
      // Payment succeeded — refresh subscription status.
      await notifier.loadStatus();
      if (context.mounted) {
        unawaited(HapticFeedback.mediumImpact());
        AeluSnackbar.show(context, 'You\'re all set — welcome to Aelu Pro.', type: SnackbarType.success);
      }
    } on StripeException catch (e) {
      if (e.error.code == FailureCode.Canceled) {
        // User dismissed the sheet — no error needed.
        return;
      }
      ErrorHandler.log('Payment Stripe error', e, StackTrace.current);
      if (context.mounted) {
        AeluSnackbar.show(context, 'Payment didn\'t go through. Try again.', type: SnackbarType.error);
      }
    } catch (e, st) {
      ErrorHandler.log('Payment checkout', e, st);
      if (context.mounted) {
        AeluSnackbar.show(context, 'Payment didn\'t go through. Try again.', type: SnackbarType.error);
      }
    }
  }

  Future<void> _confirmCancel(BuildContext context, WidgetRef ref) async {
    unawaited(HapticFeedback.selectionClick());
    final confirmed = await showModalBottomSheet<bool>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Handle bar
              Center(
                child: Container(
                  width: 36,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: AeluColors.muted.withValues(alpha: 0.3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              Text(
                'Cancel Subscription?',
                style: Theme.of(ctx).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Text(
                "You'll retain access until the end of your billing period.",
                style: Theme.of(ctx).textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(ctx, false),
                      child: const Text('Keep Plan'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () => Navigator.pop(ctx, true),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AeluColors.incorrect,
                      ),
                      child: const Text('Cancel'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    if (confirmed == true) {
      unawaited(HapticFeedback.mediumImpact());
      await ref.read(paymentProvider.notifier).cancelSubscription();
      if (context.mounted) {
        AeluSnackbar.show(
          context,
          'Subscription cancelled. You\'ll keep access through your billing period.',
          type: SnackbarType.info,
        );
      }
    }
  }
}

class _ActivePlanCard extends StatelessWidget {
  final PaymentState payment;
  const _ActivePlanCard({required this.payment});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(Icons.check_circle_outline, color: AeluColors.correctOf(context), size: 48),
            const SizedBox(height: 12),
            Text('Active: ${payment.currentPlan ?? ""}', style: theme.textTheme.titleLarge),
            if (payment.expiresAt != null)
              Text('Renews: ${payment.expiresAt}', style: theme.textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _FeatureList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const features = [
      'Unlimited practice sessions',
      'Graded reading & listening',
      'Adaptive spaced repetition',
      'HSK 1\u20136+ coverage',
      'Detailed progress tracking',
    ];

    return Column(
      children: features.map((f) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          children: [
            Icon(Icons.check_rounded, size: 18, color: AeluColors.correctOf(context)),
            const SizedBox(width: 10),
            Text(f, style: theme.textTheme.bodyMedium),
          ],
        ),
      )).toList(),
    );
  }
}

class _PlanCard extends StatelessWidget {
  final String title;
  final String price;
  final String? perMonth;
  final String? subtitle;
  final String? badge;
  final String plan;
  final VoidCallback onSelect;

  const _PlanCard({
    required this.title,
    required this.price,
    this.perMonth,
    this.subtitle,
    this.badge,
    required this.plan,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasBadge = badge != null;

    return PressableScale(
      onTap: () {
        HapticFeedback.selectionClick();
        onSelect();
      },
      child: Card(
        shape: hasBadge
            ? RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: BorderSide(color: AeluColors.accentOf(context), width: 1.5),
              )
            : null,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(title, style: theme.textTheme.titleMedium),
                        if (hasBadge) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: AeluColors.accentOf(context),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              badge!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: AeluColors.onAccent,
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (subtitle != null)
                      Text(subtitle!, style: TextStyle(color: AeluColors.correctOf(context), fontSize: 12, fontWeight: FontWeight.w600)),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(price, style: theme.textTheme.titleLarge),
                  if (perMonth != null)
                    Text(perMonth!, style: theme.textTheme.bodySmall?.copyWith(
                      color: AeluColors.mutedOf(context),
                    )),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
