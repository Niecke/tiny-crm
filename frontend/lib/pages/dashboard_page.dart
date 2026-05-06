import 'package:flutter/material.dart';

import '../api.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  late Future<String> _pingFuture;

  @override
  void initState() {
    super.initState();
    _pingFuture = _fetchPing();
  }

  Future<String> _fetchPing() async {
    final res = await dio.get<Map<String, dynamic>>('/ping');
    return res.data!['result'] as String;
  }

  @override
  Widget build(BuildContext context) {
    return Center(
      child: FutureBuilder<String>(
        future: _pingFuture,
        builder: (context, snapshot) => switch (snapshot.connectionState) {
          ConnectionState.waiting => const CircularProgressIndicator(),
          _ when snapshot.hasError => Text(
              'Error: ${snapshot.error}',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          _ => Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.check_circle_outline, size: 64, color: Colors.green),
                const SizedBox(height: 16),
                Text(
                  'Backend: ${snapshot.data}',
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ],
            ),
        },
      ),
    );
  }
}
