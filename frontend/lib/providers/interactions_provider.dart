import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/interaction.dart';
import '../repositories/interactions_repository.dart';

final interactionsRepositoryProvider = Provider<InteractionsRepository>((ref) {
  return InteractionsRepository(dio);
});

typedef InteractionsFilter = ({
  String search,
  String? contactId,
  String? kind,
  bool? upcoming,
});

/// Keyed by filter — records compare by value, so two widgets asking for the
/// same filter share one request.
final interactionsProvider =
    FutureProvider.family<List<Interaction>, InteractionsFilter>((ref, filter) {
  return ref.read(interactionsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        contactId: filter.contactId,
        kind: filter.kind,
        upcoming: filter.upcoming,
      );
});
