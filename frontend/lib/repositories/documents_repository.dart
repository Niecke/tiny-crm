import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../models/paged_result.dart';
import '../models/document.dart';

class DocumentsRepository {
  const DocumentsRepository(this._dio);

  final Dio _dio;

  Future<PagedResult<Document>> list({
    String? search,
    int skip = 0,
    int limit = kPageSize,
  }) async {
    final res = await _dio.get<Map<String, dynamic>>(
      '/documents/',
      queryParameters: <String, dynamic>{
        if (search != null && search.isNotEmpty) 'search': search,
        'skip': skip,
        'limit': limit,
      },
    );
    return PagedResult.fromJson(res.data!, Document.fromJson);
  }

  /// Every document, following pagination to the end.
  ///
  /// For pickers and id-to-name lookups, where showing only the first page
  /// would silently hide records the user knows exist. Requests the largest
  /// page the API allows, so this is one round trip until there are 200+.
  Future<List<Document>> listAll() async {
    final first = await list(limit: 200);
    final all = <Document>[...first.items];
    while (all.length < first.total) {
      final next = await list(skip: all.length, limit: 200);
      // Guard against a total that shrank mid-walk (a concurrent delete),
      // which would otherwise spin forever.
      if (next.items.isEmpty) break;
      all.addAll(next.items);
    }
    return all;
  }

  Future<Document> upload({
    required Uint8List bytes,
    required String filename,
    required String title,
    String? description,
    List<String> tags = const [],
  }) async {
    final formData = FormData.fromMap({
      'file': MultipartFile.fromBytes(bytes, filename: filename),
      'title': title,
      if (description != null && description.isNotEmpty) 'description': description,
      'tags': jsonEncode(tags),
    });
    final res = await _dio.post<Map<String, dynamic>>('/documents/', data: formData);
    return Document.fromJson(res.data!);
  }

  Future<Document> replaceContent({
    required String id,
    required Uint8List bytes,
    required String filename,
  }) async {
    final formData = FormData.fromMap({
      'file': MultipartFile.fromBytes(bytes, filename: filename),
    });
    final res = await _dio.put<Map<String, dynamic>>(
      '/documents/$id/content',
      data: formData,
    );
    return Document.fromJson(res.data!);
  }

  Future<Document> updateMetadata(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>('/documents/$id', data: data);
    return Document.fromJson(res.data!);
  }

  Future<Uint8List> downloadBytes(String id) async {
    final res = await _dio.get<List<int>>(
      '/documents/$id/content',
      options: Options(responseType: ResponseType.bytes),
    );
    if (res.statusCode != 200) throw Exception('Download failed (${res.statusCode})');
    return Uint8List.fromList(res.data!);
  }

  Future<Uint8List> downloadPreviewBytes(String id) async {
    final res = await _dio.get<List<int>>(
      '/documents/$id/preview',
      options: Options(responseType: ResponseType.bytes),
    );
    if (res.statusCode != 200) throw Exception('Preview unavailable (${res.statusCode})');
    return Uint8List.fromList(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/documents/$id');
  }
}
