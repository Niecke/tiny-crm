import 'package:dio/dio.dart';

import 'core/auth_storage.dart';

// Single Dio instance shared across all pages.
late final Dio dio;

class AuthInterceptor extends Interceptor {
  AuthInterceptor({this.onUnauthorized});

  final Future<void> Function()? onUnauthorized;

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

  @override
  Future<void> onResponse(
    Response response,
    ResponseInterceptorHandler handler,
  ) async {
    if (response.statusCode == 401) {
      await onUnauthorized?.call();
    }
    handler.next(response);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode == 401) {
      await onUnauthorized?.call();
    }
    handler.next(err);
  }
}
