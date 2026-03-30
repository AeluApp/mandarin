/// Data models for the read-only Kanban board.
class KanbanItem {
  final int id;
  final String title;
  final String status;
  final String serviceClass;
  final int? ageDays;
  final String? estimate;
  final String? dueDate;
  final String? blockedReason;
  final double? slaPct;
  final double? totalBlockedHours;

  const KanbanItem({
    required this.id,
    required this.title,
    required this.status,
    required this.serviceClass,
    this.ageDays,
    this.estimate,
    this.dueDate,
    this.blockedReason,
    this.slaPct,
    this.totalBlockedHours,
  });

  factory KanbanItem.fromJson(Map<String, dynamic> json) {
    return KanbanItem(
      id: json['id'] as int,
      title: json['title'] as String,
      status: json['status'] as String,
      serviceClass: json['service_class'] as String? ?? 'standard',
      ageDays: json['age_days'] as int?,
      estimate: json['estimate'] as String?,
      dueDate: json['due_date'] as String?,
      blockedReason: json['blocked_reason'] as String?,
      slaPct: (json['sla_pct'] as num?)?.toDouble(),
      totalBlockedHours: (json['total_blocked_hours'] as num?)?.toDouble(),
    );
  }

  /// Aging tier based on service class thresholds.
  ///
  /// Expedite: >2 days = warning, >5 days = critical.
  /// Standard/other: >14 days = warning, >21 days = critical.
  String get agingTier {
    final days = ageDays ?? 0;
    if (days <= 0) return 'normal';

    switch (serviceClass) {
      case 'expedite':
        if (days > 5) return 'critical';
        if (days > 2) return 'warning';
        return 'normal';
      case 'fixed_date':
        if (days > 10) return 'critical';
        if (days > 5) return 'warning';
        return 'normal';
      default: // standard, intangible
        if (days > 21) return 'critical';
        if (days > 14) return 'warning';
        return 'normal';
    }
  }

  bool get isBlocked => blockedReason != null && blockedReason!.isNotEmpty;
}

/// Board-level configuration including WIP limits per column.
class KanbanConfig {
  final Map<String, int> wipLimits;

  const KanbanConfig({required this.wipLimits});

  factory KanbanConfig.fromJson(Map<String, dynamic> json) {
    final limits = <String, int>{};
    final raw = json['wip_limits'] as Map<String, dynamic>? ?? {};
    for (final entry in raw.entries) {
      limits[entry.key] = entry.value as int;
    }
    return KanbanConfig(wipLimits: limits);
  }
}
