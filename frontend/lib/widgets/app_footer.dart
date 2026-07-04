import 'package:flutter/material.dart';

import '../version.dart';

/// Slim footer shown on every shell page, displaying the frontend build
/// version. The full commit hash is available on hover/long-press.
class AppFooter extends StatelessWidget {
  const AppFooter({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Tooltip(
        message: gitCommit,
        child: Text(
          'tinyCRM · $shortGitCommit',
          textAlign: TextAlign.center,
          style: Theme.of(context)
              .textTheme
              .bodySmall
              ?.copyWith(color: scheme.onSurfaceVariant),
        ),
      ),
    );
  }
}
