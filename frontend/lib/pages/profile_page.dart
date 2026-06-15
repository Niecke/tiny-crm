import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../models/user.dart';
import '../providers/user_provider.dart';

class ProfilePage extends ConsumerWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(userProfileProvider);

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 480),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: profile.when(
            loading: () => const CircularProgressIndicator(),
            error: (e, _) => Text('Failed to load profile: $e'),
            data: (user) => _ProfileContent(user: user),
          ),
        ),
      ),
    );
  }
}

class _ProfileContent extends StatelessWidget {
  const _ProfileContent({required this.user});

  final User user;

  @override
  Widget build(BuildContext context) {
    String passwordChangedLabel;
    if (user.passwordChangedAt == null) {
      passwordChangedLabel = 'Never changed';
    } else {
      final dt = user.passwordChangedAt!;
      String pad(int n) => n.toString().padLeft(2, '0');
      passwordChangedLabel =
          '${dt.year}-${pad(dt.month)}-${pad(dt.day)} ${pad(dt.hour)}:${pad(dt.minute)}';
    }

    final textTheme = Theme.of(context).textTheme;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('My account', style: textTheme.headlineSmall),
        const SizedBox(height: 24),
        _InfoRow(label: 'Name', value: user.name ?? '—'),
        const Divider(),
        _InfoRow(label: 'Email', value: user.email),
        const Divider(),
        _InfoRow(label: 'Password last changed', value: passwordChangedLabel),
        const SizedBox(height: 32),
        FilledButton.icon(
          onPressed: () => context.push('/account/password'),
          icon: const Icon(Icons.lock_outline),
          label: const Text('Change password'),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: () => context.push('/health'),
          icon: const Icon(Icons.monitor_heart_outlined),
          label: const Text('System health'),
        ),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 180,
            child: Text(label, style: textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
          ),
          Expanded(child: Text(value, style: textTheme.bodyMedium)),
        ],
      ),
    );
  }
}
