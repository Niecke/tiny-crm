import 'package:dio/dio.dart';

// Single Dio instance shared across all pages.
// One instance = one connection pool = better performance.
final dio = Dio(BaseOptions(
  baseUrl: 'http://localhost:8000',
  // Don't throw on non-2xx — let each call inspect the status itself.
  validateStatus: (status) => status != null,
));
