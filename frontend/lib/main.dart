import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

// During local dev the backend runs here. Move to a config/env later.
const _baseUrl = 'http://localhost:8000';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'tinyCRM',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo)),
      home: const StatusPage(),
    );
  }
}

// StatefulWidget — owns mutable state (the futures).
// Stateless widgets are fine for pure display; use stateful when you need
// to trigger fetches, hold data, or respond to user actions.
class StatusPage extends StatefulWidget {
  const StatusPage({super.key});

  @override
  State<StatusPage> createState() => _StatusPageState();
}

class _StatusPageState extends State<StatusPage> {
  // One Dio instance shared across calls — reuses the connection pool.
  final _dio = Dio(BaseOptions(baseUrl: _baseUrl));

  // We hold the futures as fields so hot-reload and refresh both work.
  late Future<String> _pingFuture;
  late Future<Map<String, dynamic>> _healthFuture;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  void _refresh() {
    // setState() tells Flutter to rebuild the widget tree.
    setState(() {
      _pingFuture = _fetchPing();
      _healthFuture = _fetchHealth();
    });
  }

  Future<String> _fetchPing() async {
    final res = await _dio.get<Map<String, dynamic>>('/ping');
    return res.data!['result'] as String;
  }

  Future<Map<String, dynamic>> _fetchHealth() async {
    final res = await _dio.get<Map<String, dynamic>>('/health');
    return res.data!;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('tinyCRM — Status'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _EndpointCard<String>(
            endpoint: '/ping',
            future: _pingFuture,
            // builder receives the typed data once the future resolves
            builder: (data) => Text(data),
          ),
          const SizedBox(height: 12),
          _EndpointCard<Map<String, dynamic>>(
            endpoint: '/health',
            future: _healthFuture,
            builder: (data) => Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: data.entries
                  .map((e) => Text('${e.key}: ${e.value}'))
                  .toList(),
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _refresh,
        tooltip: 'Refresh',
        child: const Icon(Icons.refresh),
      ),
    );
  }
}

// Generic card widget — works for any response type T.
// The builder callback is how the caller decides how to render T.
class _EndpointCard<T> extends StatelessWidget {
  const _EndpointCard({
    required this.endpoint,
    required this.future,
    required this.builder,
  });

  final String endpoint;
  final Future<T> future;
  final Widget Function(T data) builder;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(endpoint, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            // FutureBuilder rebuilds whenever the future's state changes:
            // waiting → has data (or error). Assign a new future to retrigger it.
            FutureBuilder<T>(
              future: future,
              builder: (context, snapshot) => switch (snapshot.connectionState) {
                ConnectionState.waiting => const CircularProgressIndicator(),
                _ when snapshot.hasError => Text(
                    'Error: ${snapshot.error}',
                    style: const TextStyle(color: Colors.red),
                  ),
                _ => builder(snapshot.data as T),
              },
            ),
          ],
        ),
      ),
    );
  }
}
