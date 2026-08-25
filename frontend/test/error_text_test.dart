import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/core/error_text.dart';

DioException _response(int status, {dynamic body, Map<String, List<String>>? headers}) {
  final options = RequestOptions(path: '/x');
  return DioException(
    requestOptions: options,
    type: DioExceptionType.badResponse,
    response: Response<dynamic>(
      requestOptions: options,
      statusCode: status,
      data: body,
      headers: Headers.fromMap(headers ?? {}),
    ),
  );
}

void main() {
  test('transport failures say what to do', () {
    expect(
      errorText(DioException(
        requestOptions: RequestOptions(path: '/x'),
        type: DioExceptionType.connectionError,
      )),
      'Cannot reach the server. Check your connection.',
    );
    expect(
      errorText(DioException(
        requestOptions: RequestOptions(path: '/x'),
        type: DioExceptionType.receiveTimeout,
      )),
      'The server did not answer in time. Please try again.',
    );
  });

  test('status codes map to plain sentences', () {
    expect(errorText(_response(401)), startsWith('Your session has expired'));
    expect(errorText(_response(403)), 'You are not allowed to do that.');
    expect(errorText(_response(404)), startsWith('Not found'));
    expect(errorText(_response(503)), 'The server had a problem (503). Please try again.');
  });

  test("the server's own detail wins when it has one", () {
    expect(
      errorText(_response(413, body: {'detail': 'File exceeds 25 MB limit'})),
      'File exceeds 25 MB limit',
    );
    // FastAPI validation errors arrive as a list of {loc, msg, type}
    expect(
      errorText(_response(422, body: {
        'detail': [
          {'loc': ['body', 'subject'], 'msg': 'Field required', 'type': 'missing'},
        ],
      })),
      'Field required',
    );
    // a detail we cannot render falls back rather than printing a Map
    expect(
      errorText(_response(400, body: {'detail': {'code': 'INVALID_PASSWORD'}})),
      'The server rejected that input.',
    );
  });

  test('rate limiting reports the wait from Retry-After', () {
    expect(
      errorText(_response(429, headers: {'retry-after': ['45']})),
      'Too many attempts. Try again in 45 seconds.',
    );
    expect(
      errorText(_response(429, headers: {'retry-after': ['300']})),
      'Too many attempts. Try again in 5 minutes.',
    );
    expect(errorText(_response(429)), startsWith('Too many attempts. Please wait'));
  });

  test('anything that is not a Dio failure still gets a sentence', () {
    expect(errorText(StateError('boom')), 'Something went wrong. Please try again.');
  });
}
