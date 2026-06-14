import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api.dart';
import 'config.dart';
import 'core/version_check.dart';
import 'features/auth/auth_provider.dart';
import 'router.dart';

void main() {
  runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();
    final config = await AppConfig.load();
    final container = ProviderContainer();
    dio = Dio(BaseOptions(
      baseUrl: config.apiUrl,
      validateStatus: (status) => status != null,
    ))..interceptors.add(AuthInterceptor(
        onUnauthorized: () => container.read(authProvider.notifier).logout(),
      ));
    runApp(UncontrolledProviderScope(container: container, child: const App()));
    VersionCheckService.start();
  }, (error, stack) {
    debugPrint('UNCAUGHT: $error\n$stack');
  });
}

class App extends ConsumerWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'tinyCRM',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF48BB78))),
      routerConfig: router,
    );
  }
}
