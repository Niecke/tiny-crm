import 'package:dio/dio.dart';

import '../models/user.dart';

class UserRepository {
  const UserRepository(this._dio);

  final Dio _dio;

  Future<User> getMe() async {
    final res = await _dio.get<Map<String, dynamic>>('/users/me');
    return User.fromJson(res.data!);
  }

  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    await _dio.post<void>(
      '/users/me/password',
      data: {'old_password': oldPassword, 'new_password': newPassword},
    );
  }
}
