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

/// Turns error responses back into thrown [DioException]s.
///
/// `validateStatus` accepts every status so [AuthInterceptor] can see a 401 in
/// `onResponse`. Without this, a 4xx/5xx body flows on as if it were a record
/// and the repositories fail while parsing it — the type error that surfaced
/// instead of the server's own message. Registered after [AuthInterceptor], so
/// the logout on 401 still runs first.
class ErrorInterceptor extends Interceptor {
  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    final status = response.statusCode ?? 0;
    if (status >= 400) {
      handler.reject(
        DioException(
          requestOptions: response.requestOptions,
          response: response,
          type: DioExceptionType.badResponse,
        ),
        true,
      );
      return;
    }
    handler.next(response);
  }
}
