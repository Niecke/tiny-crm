import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../models/document.dart';

class DocumentsRepository {
  const DocumentsRepository(this._dio);

  final Dio _dio;

  Future<List<Document>> list({String? search}) async {
    final params = <String, dynamic>{
      if (search != null && search.isNotEmpty) 'search': search,
    };
    final res = await _dio.get<List<dynamic>>(
      '/documents/',
      queryParameters: params.isEmpty ? null : params,
    );
    return res.data!
        .map((e) => Document.fromJson(e as Map<String, dynamic>))
        .toList();
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
