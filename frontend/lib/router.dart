import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:frontend/providers/tasks_provider.dart';
import 'package:go_router/go_router.dart';

import 'features/auth/auth_provider.dart';
import 'providers/contacts_provider.dart';
import 'providers/documents_provider.dart';
import 'pages/change_password_page.dart';
import 'pages/dashboard_page.dart';
import 'pages/documents_page.dart';
import 'pages/health_page.dart';
import 'pages/login_page.dart';
import 'pages/profile_page.dart';

final routerProvider = Provider<GoRouter>((ref) => _buildRouter(ref));

// Bridges Riverpod provider state changes into a ChangeNotifier so go_router
// can use it as a refreshListenable.
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(this._ref) {
    _ref.listen(authProvider, (_, _) => notifyListeners());
  }

  final Ref _ref;
}

GoRouter _buildRouter(Ref ref) {
  final listenable = _AuthListenable(ref);

  return GoRouter(
    refreshListenable: listenable,
    redirect: (context, state) {
      final authState = ref.read(authProvider);
      if (authState.isLoading) return null;

      final isLoggedIn = authState.asData?.value != null;
      final onLogin = state.matchedLocation == '/login';

      if (!isLoggedIn && !onLogin) return '/login';
      if (isLoggedIn && onLogin) return '/';
      return null;
    },
    routes: [
      ShellRoute(
        builder: (context, state, child) => AppShell(child: child),
        routes: [
          GoRoute(
            path: '/',
            builder: (context, state) => const DashboardPage(),
          ),
          GoRoute(
            path: '/documents',
            builder: (context, state) => const DocumentsPage(),
          ),
          GoRoute(
            path: '/health',
            builder: (context, state) => const HealthPage(),
          ),
          GoRoute(
            path: '/account',
            builder: (context, state) => const ProfilePage(),
          ),
          GoRoute(
            path: '/account/password',
            builder: (context, state) => const ChangePasswordPage(),
          ),
        ],
      ),
      GoRoute(path: '/login', builder: (context, state) => const LoginPage()),
    ],
  );
}

class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final location = GoRouterState.of(context).matchedLocation;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: scheme.inversePrimary,
        title: const Text('tinyCRM'),
        actions: [
          for (final (label, path) in [
            ('Dashboard', '/'),
            ('Documents', '/documents'),
            ('Health', '/health'),
          ])
            TextButton(
              onPressed: () => context.go(path),
              style: TextButton.styleFrom(
                foregroundColor: location == path
                    ? scheme.primary
                    : scheme.onSurface,
              ),
              child: Text(
                label,
                style: TextStyle(
                  fontWeight: location == path
                      ? FontWeight.bold
                      : FontWeight.normal,
                ),
              ),
            ),
          IconButton(
            onPressed: () => {
              ref.invalidate(contactsProvider),
              ref.invalidate(tasksProvider),
              ref.invalidate(documentsProvider),
            },
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
          IconButton(
            onPressed: () => context.push('/account'),
            icon: const Icon(Icons.account_circle_outlined),
            tooltip: 'My account',
          ),
          IconButton(
            onPressed: () => ref.read(authProvider.notifier).logout(),
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: child,
    );
  }
}
