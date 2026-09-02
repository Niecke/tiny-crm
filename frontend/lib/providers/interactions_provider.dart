import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/interaction.dart';
import '../models/paged_result.dart';
import '../repositories/interactions_repository.dart';

final interactionsRepositoryProvider = Provider<InteractionsRepository>((ref) {
  return InteractionsRepository(dio);
});

typedef InteractionsFilter = ({
  String search,
  String? contactId,
  String? kind,
  bool? upcoming,
  int skip,
});

/// Keyed by filter — records compare by value, so two widgets asking for the
/// same filter share one request.
final interactionsProvider =
    FutureProvider.family<PagedResult<Interaction>, InteractionsFilter>((ref, filter) {
  return ref.read(interactionsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        contactId: filter.contactId,
        kind: filter.kind,
        upcoming: filter.upcoming,
        skip: filter.skip,
      );
});

/// Interactions attached to one record — "every call about this deal".
///
/// Separate family from [interactionsProvider] so a detail screen's paging
/// cannot collide with the activity screen's own search state.
typedef AttachedInteractionsFilter = ({
  String? organizationId,
  String? dealId,
  String? projectId,
  int skip,
});

final attachedInteractionsProvider =
    FutureProvider.family<PagedResult<Interaction>, AttachedInteractionsFilter>((ref, filter) {
  return ref.read(interactionsRepositoryProvider).list(
        organizationId: filter.organizationId,
        dealId: filter.dealId,
        projectId: filter.projectId,
        skip: filter.skip,
      );
});
