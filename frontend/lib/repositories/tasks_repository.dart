import 'package:dio/dio.dart';

import '../models/task.dart';

class TasksRepository {
  const TasksRepository(this._dio);

  final Dio _dio;

  Future<List<Task>> list({String? search, bool includeDone = false}) async {
    final params = <String, dynamic>{
      if (search != null && search.isNotEmpty) 'search': search,
      if (includeDone) 'include_done': true,
    };
    final res = await _dio.get<List<dynamic>>(
      '/tasks/',
      queryParameters: params.isEmpty ? null : params,
    );
    return res.data!.map((e) => Task.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Task> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>('/tasks/', data: data);
    return Task.fromJson(res.data!);
  }

  Future<Task> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>('/tasks/$id', data: data);
    return Task.fromJson(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/tasks/$id');
  }
}
