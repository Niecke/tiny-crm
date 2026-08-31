import 'package:dio/dio.dart';

import '../models/paged_result.dart';
import '../models/contact.dart';

// All /contacts API calls live here.
// Pages talk to this class, not raw Dio — one place to change if the API shape shifts.
class ContactsRepository {
  const ContactsRepository(this._dio);

  final Dio _dio;

  /// [organizationId] narrows the list to everyone at one company.
  Future<PagedResult<Contact>> list({
    String? search,
    String? organizationId,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/contacts/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        'organization_id': ?organizationId,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Contact.fromJson);
  }

  /// Every contact, following pagination to the end.
  ///
  /// For pickers and id-to-name lookups, where showing only the first page
  /// would silently hide records the user knows exist. Requests the largest
  /// page the API allows, so this is one round trip until there are 200+.
  Future<List<Contact>> listAll() async {
    final first = await list(limit: 200);
    final all = <Contact>[...first.items];
    while (all.length < first.total) {
      final next = await list(skip: all.length, limit: 200);
      // Guard against a total that shrank mid-walk (a concurrent delete),
      // which would otherwise spin forever.
      if (next.items.isEmpty) break;
      all.addAll(next.items);
    }
    return all;
  }

  Future<Contact> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>('/contacts/', data: data);
    return Contact.fromJson(res.data!);
  }

  Future<Contact> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>(
      '/contacts/$id',
      data: data,
    );
    return Contact.fromJson(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/contacts/$id');
  }
}
