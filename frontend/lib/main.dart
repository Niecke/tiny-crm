import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
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
      // en_GB rather than en_US: it starts the week on Monday in the date
      // pickers. UI strings are the same English either way.
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('en', 'GB')],
      locale: const Locale('en', 'GB'),
      // Time pickers follow the platform's 12h/24h setting unless told
      // otherwise; the app is 24h everywhere, so force it.
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(alwaysUse24HourFormat: true),
        child: child!,
      ),
    );
  }
}
