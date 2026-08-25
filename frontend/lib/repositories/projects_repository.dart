import 'package:dio/dio.dart';

import '../models/paged_result.dart';
import '../models/project.dart';

class ProjectsRepository {
  const ProjectsRepository(this._dio);

  final Dio _dio;

  Future<PagedResult<Project>> list({
    String? search,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/projects/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Project.fromJson);
  }

  Future<Project> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>('/projects/', data: data);
    return Project.fromJson(res.data!);
  }

  Future<Project> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>(
      '/projects/$id',
      data: data,
    );
    return Project.fromJson(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/projects/$id');
  }
}
