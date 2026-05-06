import 'package:flutter/material.dart';

import '../api.dart';

class HealthPage extends StatefulWidget {
  const HealthPage({super.key});

  @override
  State<HealthPage> createState() => _HealthPageState();
}

class _HealthPageState extends State<HealthPage> {
  late Future<Map<String, dynamic>> _healthFuture;

  @override
  void initState() {
    super.initState();
    _healthFuture = _fetchHealth();
  }

  Future<Map<String, dynamic>> _fetchHealth() async {
    final res = await dio.get<Map<String, dynamic>>('/health');
    return res.data!;
  }

  void _refresh() => setState(() { _healthFuture = _fetchHealth(); });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: FutureBuilder<Map<String, dynamic>>(
        future: _healthFuture,
        builder: (context, snapshot) => switch (snapshot.connectionState) {
          ConnectionState.waiting => const CircularProgressIndicator(),
          _ when snapshot.hasError => Text(
              'Error: ${snapshot.error}',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          _ => Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ...snapshot.data!.entries.map(
                  (e) => _StatusRow(label: e.key, value: e.value as String),
                ),
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: _refresh,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh'),
                ),
              ],
            ),
        },
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  const _StatusRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final ok = value == 'ok';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            ok ? Icons.check_circle : Icons.error,
            color: ok ? Colors.green : Colors.red,
          ),
          const SizedBox(width: 12),
          Text(
            '$label: $value',
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ],
      ),
    );
  }
}
