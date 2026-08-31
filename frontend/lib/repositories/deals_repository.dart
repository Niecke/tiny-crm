import 'package:dio/dio.dart';

import '../models/deal.dart';
import '../models/paged_result.dart';

// All /deals API calls live here.
class DealsRepository {
  const DealsRepository(this._dio);

  final Dio _dio;

  /// [status] is the coarse question — see [DealStatus]. [stage] narrows to one
  /// exact column of the pipeline. Both null means everything.
  Future<PagedResult<Deal>> list({
    String? search,
    DealStage? stage,
    DealStatus? status,
    String? contactId,
    String? organizationId,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/deals/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        if (stage != null) 'stage': stage.wire,
        if (status != null) 'status': status.wire,
        'contact_id': ?contactId,
        'organization_id': ?organizationId,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Deal.fromJson);
  }

  Future<Deal> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>('/deals/', data: data);
    return Deal.fromJson(res.data!);
  }

  Future<Deal> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>('/deals/$id', data: data);
    return Deal.fromJson(res.data!);
  }

  /// Move a deal along the pipeline.
  ///
  /// Its own endpoint rather than a field on [update] because the move has
  /// consequences the server owns: it stamps the close date, pins the
  /// probability to 100 or 0, and takes the reason a deal was lost.
  Future<Deal> changeStage(String id, DealStage stage, {String? lostReason}) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/deals/$id/stage',
      data: <String, dynamic>{
        'stage': stage.wire,
        // Only ever sent with a loss — the API refuses it on any other stage.
        if (stage == DealStage.lost && lostReason != null && lostReason.isNotEmpty)
          'lost_reason': lostReason,
      },
    );
    return Deal.fromJson(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/deals/$id');
  }
}
