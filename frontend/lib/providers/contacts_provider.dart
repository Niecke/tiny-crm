import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/contact.dart';
import '../models/paged_result.dart';
import '../repositories/contacts_repository.dart';

// Provider for the repository — single instance, injected wherever needed.
// ref.read(contactsRepositoryProvider) in callbacks.
final contactsRepositoryProvider = Provider<ContactsRepository>((ref) {
  return ContactsRepository(dio);
});

typedef ContactsFilter = ({String search, String? organizationId, int skip});

/// Keyed by search text, organization and page offset — records compare by
/// value, so two widgets asking for the same page share one request. Callers
/// must reset `skip` to 0 whenever the query changes, or page 3 of the old
/// query is requested for the new one.
final contactsProvider =
    FutureProvider.family<PagedResult<Contact>, ContactsFilter>((ref, filter) {
  return ref.read(contactsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        organizationId: filter.organizationId,
        skip: filter.skip,
      );
});

/// Every contact, for pickers and id-to-name lookups. Unpaged on purpose —
/// see ContactsRepository.listAll.
final allContactsProvider = FutureProvider<List<Contact>>((ref) {
  return ref.read(contactsRepositoryProvider).listAll();
});
