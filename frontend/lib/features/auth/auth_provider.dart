import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api.dart';
import '../../core/auth_storage.dart';

// Null = unauthenticated, non-null = the access token at sign-in. The
// interceptor renews the stored token without touching this state: all the
// router needs to know is whether someone is signed in.
class AuthNotifier extends AsyncNotifier<String?> {
  @override
  Future<String?> build() => AuthStorage.readToken();

  Future<void> setTokens(String access, String refresh) async {
    await AuthStorage.writeTokens(access, refresh);
    state = AsyncData(access);
  }

  /// The Sign out button: ends the session server-side, so the tokens stop
  /// working everywhere, not just in this browser. Best effort — offline, the
  /// tokens are still dropped here and the session runs out on its own.
  Future<void> signOut() async {
    final refreshToken = await AuthStorage.readRefreshToken();
    await logout();
    if (refreshToken == null) return;
    try {
      await dio.post<void>(
        '/auth/jwt/logout',
        data: {'refresh_token': refreshToken},
      );
    } catch (_) {
      // Unreachable API; nothing more to do from here.
    }
  }

  /// Forgets the tokens locally — for a session the server already ended.
  Future<void> logout() async {
    await AuthStorage.deleteTokens();
    state = const AsyncData(null);
  }
}

final authProvider = AsyncNotifierProvider<AuthNotifier, String?>(
  AuthNotifier.new,
);
