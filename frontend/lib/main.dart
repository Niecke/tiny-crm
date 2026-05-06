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

  static const _pages = [DashboardPage(), HealthPage()];
  static const _labels = ['Dashboard', 'Health'];

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
          const SizedBox(width: 8),
        ],
      ),
      // IndexedStack keeps all pages alive — no refetch when switching tabs
      body: IndexedStack(index: _currentIndex, children: _pages),
    );
  }
}
