import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/document.dart';
import '../models/paged_result.dart';
import '../repositories/documents_repository.dart';

final documentsRepositoryProvider = Provider<DocumentsRepository>((ref) {
  return DocumentsRepository(dio);
});

typedef DocumentsFilter = ({String search, int skip});

final documentsProvider =
    FutureProvider.family<PagedResult<Document>, DocumentsFilter>((ref, filter) {
  return ref.read(documentsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        skip: filter.skip,
      );
});

/// Every document, for the project link picker.
final allDocumentsProvider = FutureProvider<List<Document>>((ref) {
  return ref.read(documentsRepositoryProvider).listAll();
});
