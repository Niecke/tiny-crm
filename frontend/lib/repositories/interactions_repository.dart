import 'package:dio/dio.dart';

import '../models/paged_result.dart';
import '../models/interaction.dart';

class InteractionsRepository {
  const InteractionsRepository(this._dio);

  final Dio _dio;

  /// [upcoming] null returns everything, true only planned entries (soonest
  /// first), false only the past activity log (newest first).
  Future<PagedResult<Interaction>> list({
    String? search,
    String? contactId,
    String? kind,
    bool? upcoming,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/interactions/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        'contact_id': ?contactId,
        'kind': ?kind,
        'upcoming': ?upcoming,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Interaction.fromJson);
  }

  Future<Interaction> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/interactions/',
      data: data,
    );
    return Interaction.fromJson(res.data!);
  }

  Future<Interaction> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>(
      '/interactions/$id',
      data: data,
    );
    return Interaction.fromJson(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/interactions/$id');
  }
}
