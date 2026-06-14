import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/document.dart';
import '../repositories/documents_repository.dart';

final documentsRepositoryProvider = Provider<DocumentsRepository>((ref) {
  return DocumentsRepository(dio);
});

final documentsProvider = FutureProvider.family<List<Document>, String>((
  ref,
  search,
) {
  return ref
      .read(documentsRepositoryProvider)
      .list(search: search.isEmpty ? null : search);
});
