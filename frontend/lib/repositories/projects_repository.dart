import 'package:dio/dio.dart';

import '../models/project.dart';

class ProjectsRepository {
  const ProjectsRepository(this._dio);

  final Dio _dio;

  Future<List<Project>> list({String? search}) async {
    final params = <String, dynamic>{
      if (search != null && search.isNotEmpty) 'search': search,
    };
    final res = await _dio.get<List<dynamic>>(
      '/projects/',
      queryParameters: params.isEmpty ? null : params,
    );
    return res.data!
        .map((e) => Project.fromJson(e as Map<String, dynamic>))
        .toList();
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
