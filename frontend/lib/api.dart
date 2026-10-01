import 'package:dio/dio.dart';

import 'core/auth_storage.dart';

// Single Dio instance shared across all pages.
late final Dio dio;

/// Adds the access token, and keeps it alive.
///
/// The access token lives 15 minutes (backend/app/auth/sessions.py), so it
/// expires all the time in an open tab. It is renewed before a request goes
/// out, and once more if the API refuses it anyway; only when the session
/// itself is over does [onUnauthorized] sign the user out.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({required String baseUrl, this.onUnauthorized})
    // Its own client, without interceptors: a refresh must not trigger one,
    // and a retried request goes back through this chain's ErrorInterceptor.
    : _plain = Dio(
        BaseOptions(
          baseUrl: baseUrl,
          validateStatus: (status) => status != null,
        ),
      );

  final Future<void> Function()? onUnauthorized;
  final Dio _plain;

  // One refresh at a time; every request that needs one waits for it. Two
  // tabs racing each other are the backend's to sort out: it answers a
  // refresh token rotated a moment ago with the same new pair.
  Future<bool>? _inFlight;

  Future<bool> _refresh() =>
      _inFlight ??= _renew().whenComplete(() => _inFlight = null);

  /// A refusal means the session is over (signed out, password changed,
  /// idle too long); offline or a 5xx leaves the tokens for the next try.
  Future<bool> _renew() async {
    final refreshToken = await AuthStorage.readRefreshToken();
    if (refreshToken == null) return false;
    try {
      final res = await _plain.post<Map<String, dynamic>>(
        '/auth/jwt/refresh',
        data: {'refresh_token': refreshToken},
      );
      if (res.statusCode != 200) return false;
      await AuthStorage.writeTokens(
        res.data!['access_token'] as String,
        res.data!['refresh_token'] as String,
      );
      return true;
    } on DioException {
      return false;
    }
  }

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    var token = await AuthStorage.readToken();
    if (token != null && expiresSoon(token)) {
      await _refresh();
      token = await AuthStorage.readToken();
    }
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
    final request = response.requestOptions;
    if (response.statusCode != 401 ||
        !request.headers.containsKey('Authorization')) {
      handler.next(response);
      return;
    }
    // Refused although it looked valid: the clock is off, or the secret it was
    // signed with has been rotated. Renew — unless another request already
    // has — and send it once more.
    final current = await AuthStorage.readToken();
    final renewedMeanwhile =
        current != null &&
        request.headers['Authorization'] != 'Bearer $current';
    if (renewedMeanwhile || await _refresh()) {
      request.headers['Authorization'] =
          'Bearer ${await AuthStorage.readToken()}';
      // A FormData body is spent once sent; a clone goes out instead.
      final body = request.data;
      if (body is FormData) request.data = body.clone();
      final retried = await _plain.fetch<dynamic>(request);
      if (retried.statusCode != 401) {
        handler.next(retried);
        return;
      }
    }
    await onUnauthorized?.call();
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
