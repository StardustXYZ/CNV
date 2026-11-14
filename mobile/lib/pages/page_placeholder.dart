import 'package:flutter/material.dart';

import '../home.dart';
import '../theme.dart';

/// A page not built yet: what it will show, what the data already says, until its phase arrives.
/// Pulling it down refreshes the data.
class PagePlaceholder extends StatelessWidget {
  const PagePlaceholder({super.key, required this.page, this.summary, this.onRefresh});

  final CnvPage page;
  final String? summary;
  final Future<void> Function()? onRefresh;

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(page.selectedIcon, size: 56, color: CnvColors.accent.withValues(alpha: 0.7)),
          const SizedBox(height: 16),
          Text(page.label, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text(page.description,
              textAlign: TextAlign.center, style: const TextStyle(fontSize: 15, color: CnvColors.textMuted, height: 1.4)),
          if (summary != null) ...[
            const SizedBox(height: 14),
            Text(summary!, textAlign: TextAlign.center, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          ],
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: CnvColors.surface2,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(color: CnvColors.border),
            ),
            child: const Text('In arrivo nelle prossime versioni', style: TextStyle(fontSize: 12, color: CnvColors.textMuted)),
          ),
        ],
      ),
    );
    return RefreshIndicator(
      onRefresh: onRefresh ?? () async {},
      child: LayoutBuilder(
        builder: (context, box) => ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [ConstrainedBox(constraints: BoxConstraints(minHeight: box.maxHeight), child: Center(child: content))],
        ),
      ),
    );
  }
}
