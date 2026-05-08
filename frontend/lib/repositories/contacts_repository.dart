import 'package:dio/dio.dart';

import '../models/contact.dart';

// All /contacts API calls live here.
// Pages talk to this class, not raw Dio — one place to change if the API shape shifts.
class ContactsRepository {
  const ContactsRepository(this._dio);

  final Dio _dio;

  Future<List<Contact>> list() async {
    final res = await _dio.get<List<dynamic>>('/contacts/');
    return res.data!.map((e) => Contact.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Contact> create(Map<String, dynamic> data) async {
    final res = await _dio.post<Map<String, dynamic>>('/contacts/', data: data);
    return Contact.fromJson(res.data!);
  }

  Future<Contact> update(String id, Map<String, dynamic> data) async {
    final res = await _dio.patch<Map<String, dynamic>>('/contacts/$id', data: data);
    return Contact.fromJson(res.data!);
  }

  Future<void> delete(String id) async {
    await _dio.delete('/contacts/$id');
  }
}
