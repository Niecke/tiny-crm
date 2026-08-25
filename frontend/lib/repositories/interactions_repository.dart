import 'package:dio/dio.dart';

import '../models/interaction.dart';

class InteractionsRepository {
  const InteractionsRepository(this._dio);

  final Dio _dio;

  /// [upcoming] null returns everything, true only planned entries (soonest
  /// first), false only the past activity log (newest first).
  Future<List<Interaction>> list({
    String? search,
    String? contactId,
    String? kind,
    bool? upcoming,
  }) async {
    final params = <String, dynamic>{
      if (search != null && search.isNotEmpty) 'search': search,
      'contact_id': ?contactId,
      'kind': ?kind,
      'upcoming': ?upcoming,
    };
    final res = await _dio.get<List<dynamic>>(
      '/interactions/',
      queryParameters: params.isEmpty ? null : params,
    );
    return res.data!
        .map((e) => Interaction.fromJson(e as Map<String, dynamic>))
        .toList();
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
