import 'package:dio/dio.dart';

import '../models/paged_result.dart';
import '../models/task.dart';

class TasksRepository {
  const TasksRepository(this._dio);

  final Dio _dio;

  /// [contactId], [dealId] and [interactionId] answer "what do I owe this
  /// record?" — the question tasks-on-projects could not.
  Future<PagedResult<Task>> list({
    String? search,
    bool includeDone = false,
    String? contactId,
    String? dealId,
    String? interactionId,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/tasks/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        if (includeDone) 'include_done': true,
        'contact_id': ?contactId,
        'deal_id': ?dealId,
        'interaction_id': ?interactionId,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Task.fromJson);
  }

  /// Every task, following pagination to the end.
  ///
  /// For pickers and id-to-name lookups, where showing only the first page
  /// would silently hide records the user knows exist. Requests the largest
  /// page the API allows, so this is one round trip until there are 200+.
  Future<List<Task>> listAll() async {
    final first = await list(includeDone: true, limit: 200);
    final all = <Task>[...first.items];
    while (all.length < first.total) {
      final next = await list(includeDone: true, skip: all.length, limit: 200);
      // Guard against a total that shrank mid-walk (a concurrent delete),
      // which would otherwise spin forever.
      if (next.items.isEmpty) break;
      all.addAll(next.items);
    }
    return all;
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
