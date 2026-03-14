import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_response.dart';
import '../core/error_handler.dart';

class PaymentState {
  final String? currentPlan;
  final bool isActive;
  final String? expiresAt;
  final bool loading;

  const PaymentState({
    this.currentPlan,
    this.isActive = false,
    this.expiresAt,
    this.loading = true,
  });

  PaymentState copyWith({
    String? currentPlan,
    bool? isActive,
    String? expiresAt,
    bool? loading,
  }) {
    return PaymentState(
      currentPlan: currentPlan ?? this.currentPlan,
      isActive: isActive ?? this.isActive,
      expiresAt: expiresAt ?? this.expiresAt,
      loading: loading ?? this.loading,
    );
  }
}

class PaymentNotifier extends StateNotifier<PaymentState> {
  final ApiClient _api;

  PaymentNotifier(this._api) : super(const PaymentState());

  Future<void> loadStatus() async {
    try {
      final response = await _api.get('/api/subscription/status');
      final data = SafeMap.from(response.data);
      if (data == null) return;
      state = PaymentState(
        currentPlan: data.strOrNull('plan'),
        isActive: data.boolean('active'),
        expiresAt: data.strOrNull('expires_at'),
        loading: false,
      );
    } catch (e, st) {
      ErrorHandler.log('Payment load status', e, st);
      state = state.copyWith(loading: false);
    }
  }

  Future<String?> createCheckoutSession(String plan) async {
    // SECURITY: Validate plan against allowlist.
    const validPlans = {'monthly', 'annual'};
    if (!validPlans.contains(plan)) return null;
    try {
      final response = await _api.post('/api/checkout', data: {'plan': plan});
      final data = SafeMap.from(response.data);
      if (data == null) return null;
      return data.strOrNull('client_secret');
    } catch (e, st) {
      ErrorHandler.log('Payment create checkout', e, st);
      return null;
    }
  }

  Future<void> cancelSubscription() async {
    try {
      await _api.post('/api/subscription/cancel');
      await loadStatus();
    } catch (e, st) {
      ErrorHandler.log('Payment cancel subscription', e, st);
    }
  }
}

final paymentProvider = StateNotifierProvider<PaymentNotifier, PaymentState>((ref) {
  final api = ref.watch(apiClientProvider);
  final notifier = PaymentNotifier(api);
  notifier.loadStatus();
  return notifier;
});
