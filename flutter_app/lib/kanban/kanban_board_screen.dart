import 'package:flutter/material.dart';

import '../theme/aelu_colors.dart';
import 'kanban_models.dart';

/// Column definitions for the Kanban board.
const _columns = ['backlog', 'ready', 'in_progress', 'review', 'done'];

const _columnLabels = {
  'backlog': 'Backlog',
  'ready': 'Ready',
  'in_progress': 'In Progress',
  'review': 'Review',
  'done': 'Done',
};

/// Read-only Kanban board screen for monitoring work items.
///
/// Horizontally scrollable with five columns. Cards show title, service class
/// indicator, age badge, and SLA timer. No drag-and-drop — this is a
/// monitoring view only.
class KanbanBoardScreen extends StatelessWidget {
  final List<KanbanItem> items;
  final KanbanConfig config;

  const KanbanBoardScreen({
    super.key,
    required this.items,
    required this.config,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (items.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: const Text('Board')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Text(
              'No work items yet',
              style: theme.textTheme.bodyLarge?.copyWith(
                color: _textDimOf(context),
              ),
            ),
          ),
        ),
      );
    }

    // Group items by status column.
    final grouped = <String, List<KanbanItem>>{};
    for (final col in _columns) {
      grouped[col] = [];
    }
    for (final item in items) {
      final col = _columns.contains(item.status) ? item.status : 'backlog';
      grouped[col]!.add(item);
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Board')),
      body: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: _columns
              .map((col) => _KanbanColumn(
                    columnKey: col,
                    label: _columnLabels[col] ?? col,
                    items: grouped[col] ?? [],
                    wipLimit: config.wipLimits[col],
                  ))
              .toList(),
        ),
      ),
    );
  }
}

// ── Column ──

class _KanbanColumn extends StatelessWidget {
  final String columnKey;
  final String label;
  final List<KanbanItem> items;
  final int? wipLimit;

  const _KanbanColumn({
    required this.columnKey,
    required this.label,
    required this.items,
    this.wipLimit,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final count = items.length;
    final overWip = wipLimit != null && count > wipLimit!;

    // Column header text: "In Progress 3/5" or "Backlog 12".
    final headerCount = wipLimit != null ? '$count/$wipLimit' : '$count';

    return SizedBox(
      width: 260,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.only(bottom: 10, left: 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      label,
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  Text(
                    headerCount,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: overWip
                          ? AeluColors.incorrectOf(context)
                          : _textDimOf(context),
                      fontWeight: overWip ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ],
              ),
            ),

            // Divider
            Container(
              height: 0.5,
              color: isDark ? AeluColors.dividerDark : AeluColors.divider,
            ),
            const SizedBox(height: 8),

            // Cards
            Expanded(
              child: ListView.separated(
                itemCount: items.length,
                separatorBuilder: (_, __) => const SizedBox(height: 8),
                itemBuilder: (context, index) =>
                    _KanbanCard(item: items[index]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Card ──

class _KanbanCard extends StatelessWidget {
  final KanbanItem item;

  const _KanbanCard({required this.item});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final cardBg = isDark ? AeluColors.surfaceAltDark : AeluColors.surfaceAltLight;
    final agingTint = _agingTintColor(context, item.agingTier);
    final serviceColor = _serviceClassColor(context, item.serviceClass);
    final dimColor = _textDimOf(context);

    return Semantics(
      label: _semanticsLabel,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOutCubic,
        decoration: BoxDecoration(
          color: agingTint ?? cardBg,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Opacity(
          opacity: item.isBlocked ? 0.7 : 1.0,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Service class left border indicator.
                if (serviceColor != Colors.transparent)
                  Container(
                    width: 3,
                    height: 40,
                    margin: const EdgeInsets.only(right: 10),
                    decoration: BoxDecoration(
                      color: serviceColor,
                      borderRadius: BorderRadius.circular(1.5),
                    ),
                  ),

                // Content
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Title
                      Text(
                        item.title,
                        style: theme.textTheme.bodyMedium,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),

                      const SizedBox(height: 6),

                      // Age badge + SLA row
                      Row(
                        children: [
                          if (item.ageDays != null) ...[
                            _AgeBadge(
                              days: item.ageDays!,
                              tier: item.agingTier,
                            ),
                            const SizedBox(width: 8),
                          ],
                          if (item.slaPct != null)
                            _SlaTimer(
                              pct: item.slaPct!,
                            ),
                        ],
                      ),

                      // Blocked reason
                      if (item.isBlocked) ...[
                        const SizedBox(height: 6),
                        Text(
                          item.blockedReason!,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: dimColor,
                            fontStyle: FontStyle.italic,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String get _semanticsLabel {
    final parts = <String>[item.title];
    if (item.ageDays != null) parts.add('${item.ageDays} days old');
    if (item.isBlocked) parts.add('blocked: ${item.blockedReason}');
    if (item.slaPct != null) parts.add('${item.slaPct!.round()}% of SLA consumed');
    parts.add('service class: ${item.serviceClass}');
    return parts.join(', ');
  }
}

// ── Age badge ──

class _AgeBadge extends StatelessWidget {
  final int days;
  final String tier;

  const _AgeBadge({required this.days, required this.tier});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = switch (tier) {
      'critical' => AeluColors.incorrectOf(context),
      'warning' => AeluColors.accentOf(context),
      _ => _textDimOf(context),
    };

    return Text(
      '${days}d',
      style: theme.textTheme.bodySmall?.copyWith(
        color: color,
        fontWeight: tier == 'normal' ? FontWeight.w400 : FontWeight.w600,
      ),
    );
  }
}

// ── SLA timer ──

class _SlaTimer extends StatelessWidget {
  final double pct;

  const _SlaTimer({required this.pct});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = pct > 85
        ? AeluColors.incorrectOf(context)
        : pct > 60
            ? AeluColors.accentOf(context)
            : _textDimOf(context);

    return Text(
      '${pct.round()}% SLA',
      style: theme.textTheme.bodySmall?.copyWith(
        color: color,
        fontWeight: pct > 85 ? FontWeight.w600 : FontWeight.w400,
      ),
    );
  }
}

// ── Helpers ──

Color _textDimOf(BuildContext context) {
  return Theme.of(context).brightness == Brightness.dark
      ? AeluColors.textDimDark
      : AeluColors.textDimLight;
}

Color _serviceClassColor(BuildContext context, String serviceClass) {
  return switch (serviceClass) {
    'expedite' => AeluColors.incorrectOf(context),
    'fixed_date' => AeluColors.accentOf(context),
    'standard' => _textDimOf(context),
    'intangible' => Colors.transparent,
    _ => _textDimOf(context),
  };
}

/// Returns a tinted background for aging cards, or null for normal.
Color? _agingTintColor(BuildContext context, String tier) {
  final isDark = Theme.of(context).brightness == Brightness.dark;

  return switch (tier) {
    'warning' => isDark
        ? const Color(0xFF3A3020) // warm amber tint on dark
        : const Color(0xFFF5ECD0), // warm amber tint on light
    'critical' => AeluColors.incorrectOf(context).withValues(alpha: 0.08),
    _ => null,
  };
}
