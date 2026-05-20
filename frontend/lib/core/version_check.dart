import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

const String _appVersion = String.fromEnvironment('APP_VERSION', defaultValue: 'dev');

@JS('window.location.reload')
external void _reload();

class VersionCheckService {
  static void start() {
    if (!kIsWeb || _appVersion == 'dev') return;
    Timer.periodic(const Duration(minutes: 1), (_) => _check());
  }

  static Future<void> _check() async {
    try {
      final res = await Dio().get<String>(
        '/version.json',
        queryParameters: {'t': DateTime.now().millisecondsSinceEpoch},
        options: Options(
          responseType: ResponseType.plain,
          sendTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 5),
        ),
      );
      final data = jsonDecode(res.data!) as Map<String, dynamic>;
      final remoteVersion = data['version'] as String;
      if (remoteVersion != _appVersion) {
        _reload();
      }
    } catch (_) {
      // network error — skip, retry next tick
    }
  }
}
