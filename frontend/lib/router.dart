import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:frontend/providers/tasks_provider.dart';
import 'package:go_router/go_router.dart';

import 'features/auth/auth_provider.dart';
import 'providers/contacts_provider.dart';
import 'providers/deals_provider.dart';
import 'providers/documents_provider.dart';
import 'providers/interactions_provider.dart';
import 'providers/organizations_provider.dart';
import 'providers/projects_provider.dart';
import 'providers/watches_provider.dart';
import 'pages/change_password_page.dart';
import 'pages/dashboard_page.dart';
import 'pages/deals_page.dart';
import 'pages/documents_page.dart';
import 'pages/health_page.dart';
import 'pages/interactions_page.dart';
import 'pages/login_page.dart';
import 'pages/organizations_page.dart';
import 'pages/profile_page.dart';
import 'pages/projects_page.dart';
import 'pages/watches_page.dart';
import 'widgets/app_footer.dart';

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
            path: '/organizations',
            builder: (context, state) => const OrganizationsPage(),
          ),
          GoRoute(
            path: '/deals',
            builder: (context, state) => const DealsPage(),
          ),
          GoRoute(
            path: '/watches',
            builder: (context, state) => const WatchesPage(),
          ),
          GoRoute(
            path: '/projects',
            builder: (context, state) => const ProjectsPage(),
          ),
          GoRoute(
            path: '/documents',
            builder: (context, state) => const DocumentsPage(),
          ),
          GoRoute(
            path: '/interactions',
            builder: (context, state) => const InteractionsPage(),
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
    final isWide = MediaQuery.of(context).size.width >= 700;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: scheme.inversePrimary,
        leading: isWide
            ? null
            : InkWell(
                onTap: () => context.go('/'),
                borderRadius: BorderRadius.circular(9),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Container(
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: scheme.outlineVariant,
                        width: 1.5,
                      ),
                      borderRadius: BorderRadius.circular(9),
                    ),
                    child: Image.asset('web/favicon.png'),
                  ),
                ),
              ),
        title: isWide ? const Text('tinyCRM') : null,
        actions: [
          if (isWide)
            for (final (label, path) in [
              ('Dashboard', '/'),
              ('Sources', '/watches'),
              ('Deals', '/deals'),
              ('Organizations', '/organizations'),
              ('Projects', '/projects'),
              ('Documents', '/documents'),
              ('Activity', '/interactions'),
            ])
              TextButton(
                onPressed: () => context.go(path),
                style: TextButton.styleFrom(
                  foregroundColor: location == path
                      ? scheme.primary
                      : scheme.onSurface,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      label,
                      style: TextStyle(
                        fontWeight: location == path
                            ? FontWeight.bold
                            : FontWeight.normal,
                      ),
                    ),
                    // How many sources are due, so the sweep is visible without
                    // opening the screen — a watch list nobody looks at is the
                    // failure mode this whole feature exists to avoid.
                    if (path == '/watches') const _DueWatchBadge(),
                  ],
                ),
              )
          else
            PopupMenuButton<String>(
              icon: const Icon(Icons.menu),
              tooltip: 'Navigate',
              onSelected: context.go,
              itemBuilder: (_) => const [
                PopupMenuItem(value: '/watches', child: Text('Sources')),
                PopupMenuItem(value: '/deals', child: Text('Deals')),
                PopupMenuItem(
                  value: '/organizations',
                  child: Text('Organizations'),
                ),
                PopupMenuItem(value: '/projects', child: Text('Projects')),
                PopupMenuItem(value: '/documents', child: Text('Documents')),
                PopupMenuItem(
                  value: '/interactions',
                  child: Text('Activity'),
                ),
              ],
            ),
          IconButton(
            onPressed: () => {
              ref.invalidate(contactsProvider),
              ref.invalidate(allContactsProvider),
              ref.invalidate(organizationsProvider),
              ref.invalidate(allOrganizationsProvider),
              ref.invalidate(dealsProvider),
              ref.invalidate(watchesProvider),
              ref.invalidate(dueWatchCountProvider),
              ref.invalidate(tasksProvider),
              ref.invalidate(allTasksProvider),
              ref.invalidate(documentsProvider),
              ref.invalidate(allDocumentsProvider),
              ref.invalidate(projectsProvider),
              ref.invalidate(interactionsProvider),
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
      body: Column(
        children: [
          Expanded(child: child),
          const AppFooter(),
        ],
      ),
    );
  }
}

/// The count of sources due for a sweep, beside the Sources nav item.
///
/// Silent when nothing is due and while the count is loading — a badge that
/// flashes "0" on every navigation is noise, and a failure here must never
/// break the app bar.
class _DueWatchBadge extends ConsumerWidget {
  const _DueWatchBadge();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final due = ref.watch(dueWatchCountProvider).asData?.value ?? 0;
    if (due == 0) return const SizedBox.shrink();

    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(left: 6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
        decoration: BoxDecoration(
          color: scheme.primary,
          borderRadius: BorderRadius.circular(10),
        ),
        child: Text(
          '$due',
          style: TextStyle(
            color: scheme.onPrimary,
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }
}
