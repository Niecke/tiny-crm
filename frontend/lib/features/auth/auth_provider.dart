import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/auth_storage.dart';

// Null = unauthenticated, non-null = JWT token
class AuthNotifier extends AsyncNotifier<String?> {
  @override
  Future<String?> build() => AuthStorage.readToken();

  Future<void> setToken(String token) async {
    await AuthStorage.writeToken(token);
    state = AsyncData(token);
  }

  Future<void> logout() async {
    await AuthStorage.deleteToken();
    state = const AsyncData(null);
  }
}

final authProvider = AsyncNotifierProvider<AuthNotifier, String?>(AuthNotifier.new);
