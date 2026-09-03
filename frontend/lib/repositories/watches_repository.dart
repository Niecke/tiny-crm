import 'package:dio/dio.dart';

import '../models/paged_result.dart';
import '../models/watch.dart';

// All /watches API calls live here.
class WatchesRepository {
  const WatchesRepository(this._dio);

  final Dio _dio;

  /// [due] true is the sweep list: everything due now or overdue.
  Future<PagedResult<Watch>> list({
    String? search,
    WatchKind? kind,
    String? organizationId,
    bool? due,
    bool? active,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/watches/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        if (kind != null) 'kind': kind.wire,
        'organization_id': ?organizationId,
        'due': ?due,
        'active': ?active,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Watch.fromJson);
  }

  Future<Watch> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>('/watches/', data: data);
    return Watch.fromJson(res.data!);
  }

  Future<Watch> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>('/watches/$id', data: data);
    return Watch.fromJson(res.data!);
  }

  /// Record one sweep, which also advances the cadence and — when something was
  /// found — creates the deal or task it produced.
  ///
  /// One call rather than three: a check that logged but failed to advance the
  /// cadence would come straight back as due, and a deal created separately
  /// could end up with no check pointing at it.
  Future<WatchCheckResult> check(
    String id, {
    CheckOutcome outcome = CheckOutcome.nothing,
    String? note,
    Map<String, dynamic>? createDeal,
    Map<String, dynamic>? createTask,
  }) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/watches/$id/check',
      data: <String, dynamic>{
        'outcome': outcome.wire,
        'note': ?note,
        // The API refuses either of these unless something was actually found.
        if (outcome == CheckOutcome.found) 'create_deal': ?createDeal,
        if (outcome == CheckOutcome.found) 'create_task': ?createTask,
      },
    );
    return WatchCheckResult.fromJson(res.data!);
  }

  /// This source's history, newest first.
  Future<PagedResult<WatchCheck>> checks(
    String id, {
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/watches/$id/checks',
      queryParameters: <String, dynamic>{'skip': skip, 'limit': limit},
    );
    return PagedResult.fromJson(res.data!, WatchCheck.fromJson);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/watches/$id');
  }
}
