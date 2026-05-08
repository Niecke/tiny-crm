import 'dart:convert';

import 'package:dio/dio.dart';

class AppConfig {
  final String apiUrl;
  AppConfig({required this.apiUrl});

  static Future<AppConfig> load() async {
    try {
      final res = await Dio().get<String>(
        '/config.json',
        options: Options(responseType: ResponseType.plain),
      );
      final data = jsonDecode(res.data!) as Map<String, dynamic>;
      return AppConfig(apiUrl: data['apiUrl'] as String);
    } catch (_) {
      return AppConfig(apiUrl: 'http://localhost:8000');
    }
  }
}
