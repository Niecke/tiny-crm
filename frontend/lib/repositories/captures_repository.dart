import 'package:dio/dio.dart';

import '../models/capture.dart';
import '../models/paged_result.dart';

// All /captures API calls live here.
class CapturesRepository {
  const CapturesRepository(this._dio);

  final Dio _dio;

  /// [status] null means every status — the "what did I do with that link?"
  /// question rather than the daily one.
  Future<PagedResult<Capture>> list({
    CaptureStatus? status = CaptureStatus.isNew,
    String? search,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/captures/',
      queryParameters: <String, dynamic>{
        'status': status?.wire ?? 'all',
        if (search != null && search.isNotEmpty) 'search': search,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Capture.fromJson);
  }

  /// Park one line. [raw] is the only thing the API needs; it pulls the name
  /// and the link out itself.
  ///
  /// [name] and [url] are for the share target, which already has the URL
  /// Android handed it and should not make the parser take a string apart
  /// again to find it.
  Future<Capture> create(String raw, {String? name, String? url, String? note}) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/captures/',
      data: <String, dynamic>{'raw': raw, 'name': ?name, 'url': ?url, 'note': ?note},
    );
    return Capture.fromJson(res.data!);
  }

  Future<Capture> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>('/captures/$id', data: data);
    return Capture.fromJson(res.data!);
  }

  /// Work one capture: who they are, the lead it opens, the message you sent.
  ///
  /// One call rather than four, because the four belong together — a contact
  /// created without its deal is a name nobody follows up, and a deal created
  /// without the capture being stamped comes back in tomorrow's inbox.
  ///
  /// Exactly one of [contactId] and [contact]; the API refuses both or neither.
  Future<CaptureConvertResult> convert(
    String id, {
    String? contactId,
    Map<String, dynamic>? contact,
    Map<String, dynamic>? deal,
    Map<String, dynamic>? interaction,
  }) async {
    final res = await _dio.post<Map<String, dynamic>>(
      '/captures/$id/convert',
      data: <String, dynamic>{
        'contact_id': ?contactId,
        'contact': ?contact,
        'deal': ?deal,
        'interaction': ?interaction,
      },
    );
    return CaptureConvertResult.fromJson(res.data!);
  }

  /// Decide not to pursue this one. Kept rather than deleted: an inbox that
  /// forgets its own rejections offers them again next month.
  Future<Capture> dismiss(String id) async {
    final res = await _dio.post<Map<String, dynamic>>('/captures/$id/dismiss');
    return Capture.fromJson(res.data!);
  }

  /// Remove it outright — what Undo in the quick-add box calls. A typo is not
  /// a decision, so it leaves no dismissed row behind.
  Future<void> delete(String id) async {
    await _dio.delete('/captures/$id');
  }

  Future<CaptureCount> count() async {
    final res = await _dio.get<Map<String, dynamic>>('/captures/count');
    return CaptureCount.fromJson(res.data!);
  }
}
