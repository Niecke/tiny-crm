import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

// A login is a pair (backend/app/auth/sessions.py): a 15-minute access token
// and the refresh token that renews it. AuthInterceptor does the renewing.
const _tokenKey = 'jwt_token';
const _refreshKey = 'refresh_token';

class AuthStorage {
  static const _storage = FlutterSecureStorage();

  static Future<String?> readToken() => _storage.read(key: _tokenKey);

  static Future<String?> readRefreshToken() => _storage.read(key: _refreshKey);

  static Future<void> writeTokens(String access, String refresh) async {
    await _storage.write(key: _tokenKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  static Future<void> deleteTokens() async {
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _refreshKey);
  }
}

/// Whether [token] expires within [margin] — renewed before it goes out, so a
/// request never leaves with a token that dies on the way. Reads the JWT's own
/// `exp`; an unreadable token counts as expiring.
bool expiresSoon(
  String token, {
  Duration margin = const Duration(seconds: 30),
}) {
  try {
    final payload = token.split('.')[1];
    final claims = jsonDecode(
      utf8.decode(base64Url.decode(base64Url.normalize(payload))),
    );
    final exp = claims['exp'];
    if (exp is! num) return true;
    final expiry = DateTime.fromMillisecondsSinceEpoch(
      (exp * 1000).toInt(),
      isUtc: true,
    );
    return DateTime.now().toUtc().add(margin).isAfter(expiry);
  } catch (_) {
    return true;
  }
}
