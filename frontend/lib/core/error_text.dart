import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

/// One sentence the user can act on, for anything an API call threw.
///
/// Rendering the raw object gives a Dio stack description
/// ("DioException [bad response]: This exception was thrown because…"),
/// which says nothing about what went wrong or what to do next.
String errorText(Object error) {
  if (error is DioException) return _dioText(error);
  return 'Something went wrong. Please try again.';
}

String _dioText(DioException error) {
  switch (error.type) {
    case DioExceptionType.connectionTimeout:
    case DioExceptionType.sendTimeout:
    case DioExceptionType.receiveTimeout:
    case DioExceptionType.transformTimeout:
      return 'The server did not answer in time. Please try again.';
    case DioExceptionType.connectionError:
      return 'Cannot reach the server. Check your connection.';
    case DioExceptionType.badCertificate:
      return 'The server certificate was rejected.';
    case DioExceptionType.cancel:
      return 'The request was cancelled.';
    case DioExceptionType.badResponse:
    case DioExceptionType.unknown:
      return _statusText(error.response);
  }
}

String _statusText(Response<dynamic>? response) {
  final status = response?.statusCode;
  final detail = _detail(response);
  return switch (status) {
    null => 'Something went wrong. Please try again.',
    400 || 422 => detail ?? 'The server rejected that input.',
    401 => 'Your session has expired. Please sign in again.',
    403 => 'You are not allowed to do that.',
    404 => 'Not found — it may have been deleted already.',
    409 => detail ?? 'That conflicts with something that already exists.',
    413 => detail ?? 'That file is too large.',
    429 => _retryText(response),
    >= 500 => 'The server had a problem ($status). Please try again.',
    _ => detail ?? 'Request failed ($status).',
  };
}

String _retryText(Response<dynamic>? response) {
  final seconds = int.tryParse(response?.headers.value('retry-after') ?? '');
  if (seconds == null) {
    return 'Too many attempts. Please wait a moment and try again.';
  }
  if (seconds < 60) return 'Too many attempts. Try again in $seconds seconds.';
  final minutes = (seconds / 60).ceil();
  return 'Too many attempts. Try again in $minutes '
      '${minutes == 1 ? 'minute' : 'minutes'}.';
}

/// FastAPI puts the readable part in `detail` — either a string, or the
/// validation list of `{loc, msg, type}` objects.
String? _detail(Response<dynamic>? response) {
  final data = response?.data;
  if (data is! Map) return null;
  final detail = data['detail'];
  if (detail is String) return detail.isEmpty ? null : detail;
  if (detail is List && detail.isNotEmpty) {
    final first = detail.first;
    if (first is Map && first['msg'] is String) return first['msg'] as String;
  }
  return null;
}

/// Reports a failed action in place, without losing the user's context.
/// [prefix] names the action ("Delete failed."); the rest says why.
void showErrorSnackBar(BuildContext context, Object error, {String? prefix}) {
  final message = errorText(error);
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(prefix == null ? message : '$prefix $message')),
  );
}
