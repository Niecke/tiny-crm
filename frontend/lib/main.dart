import 'package:flutter/material.dart';

import 'pages/dashboard_page.dart';
import 'pages/health_page.dart';

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
      home: const AppShell(),
    );
  }
}

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _currentIndex = 0;
  int _refreshCounter = 0;

  static const _labels = ['Dashboard', 'Health'];

  void _refresh() => setState(() => _refreshCounter++);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: scheme.inversePrimary,
        title: const Text('tinyCRM'),
        actions: [
          for (int i = 0; i < _labels.length; i++)
            TextButton(
              onPressed: () => setState(() => _currentIndex = i),
              style: TextButton.styleFrom(
                foregroundColor: _currentIndex == i ? scheme.primary : scheme.onSurface,
              ),
              child: Text(
                _labels[i],
                style: TextStyle(fontWeight: _currentIndex == i ? FontWeight.bold : FontWeight.normal),
              ),
            ),
          IconButton(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
          const SizedBox(width: 8),
        ],
      ),
      // New ValueKey on each refresh → Flutter recreates the page → initState reruns → data refetched
      body: IndexedStack(
        index: _currentIndex,
        children: [
          DashboardPage(key: ValueKey('dash_$_refreshCounter')),
          HealthPage(key: ValueKey('health_$_refreshCounter')),
        ],
      ),
    );
  }
}
