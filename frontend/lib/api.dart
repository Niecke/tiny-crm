import 'package:dio/dio.dart';

import 'core/auth_storage.dart';

// Single Dio instance shared across all pages.
final dio = Dio(BaseOptions(
  baseUrl: 'http://localhost:8000',
  validateStatus: (status) => status != null,
))..interceptors.add(_AuthInterceptor());

class _AuthInterceptor extends Interceptor {
  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await AuthStorage.readToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}
