import 'package:dio/dio.dart';

import '../models/organization.dart';
import '../models/paged_result.dart';

// All /organizations API calls live here.
class OrganizationsRepository {
  const OrganizationsRepository(this._dio);

  final Dio _dio;

  /// [search] matches the name or the domain — an email signature often gives
  /// the domain and nothing else.
  Future<PagedResult<Organization>> list({
    String? search,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/organizations/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Organization.fromJson);
  }

  /// Every organization, following pagination to the end.
  ///
  /// For the picker on the contact form, where showing only the first page
  /// would hide companies the user knows exist. See ContactsRepository.listAll.
  Future<List<Organization>> listAll() async {
    final first = await list(limit: 200);
    final all = <Organization>[...first.items];
    while (all.length < first.total) {
      final next = await list(skip: all.length, limit: 200);
      // Guard against a total that shrank mid-walk (a concurrent delete),
      // which would otherwise spin forever.
      if (next.items.isEmpty) break;
      all.addAll(next.items);
    }
    return all;
  }

  Future<Organization> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/organizations/',
      data: data,
    );
    return Organization.fromJson(res.data!);
  }

  Future<Organization> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>(
      '/organizations/$id',
      data: data,
    );
    return Organization.fromJson(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/organizations/$id');
  }
}
