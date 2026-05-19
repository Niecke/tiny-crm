import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/user.dart';
import '../repositories/user_repository.dart';

final userRepositoryProvider = Provider<UserRepository>((ref) {
  return UserRepository(dio);
});

final userProfileProvider = FutureProvider<User>((ref) {
  return ref.read(userRepositoryProvider).getMe();
});
