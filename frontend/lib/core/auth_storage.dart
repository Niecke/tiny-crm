import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _tokenKey = 'jwt_token';

class AuthStorage {
  static const _storage = FlutterSecureStorage();

  static Future<String?> readToken() => _storage.read(key: _tokenKey);

  static Future<void> writeToken(String token) =>
      _storage.write(key: _tokenKey, value: token);

  static Future<void> deleteToken() => _storage.delete(key: _tokenKey);
}
