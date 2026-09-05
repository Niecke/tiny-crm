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

/// `lifecycleStatus` and `relationType` are deliberately separate: status is
/// how far along we are, type is what this party is to me, and sending both
/// narrows to the row worth acting on. `worksWithFreelancers` is tri-state so
/// the never-asked ones can be asked for.
typedef ContactsFilter = ({
  String search,
  String? organizationId,
  LifecycleStatus? lifecycleStatus,
  RelationType? relationType,
  FreelancerAnswer? worksWithFreelancers,
  int skip,
});

/// Keyed by the whole filter — records compare by value, so two widgets asking
/// for the same page share one request. Callers must reset `skip` to 0 whenever
/// anything else in the filter changes, or page 3 of the old query is requested
/// for the new one.
final contactsProvider =
    FutureProvider.family<PagedResult<Contact>, ContactsFilter>((ref, filter) {
  return ref.read(contactsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        organizationId: filter.organizationId,
        lifecycleStatus: filter.lifecycleStatus,
        relationType: filter.relationType,
        worksWithFreelancers: filter.worksWithFreelancers,
        skip: filter.skip,
      );
});

/// Every contact, for pickers and id-to-name lookups. Unpaged on purpose —
/// see ContactsRepository.listAll.
final allContactsProvider = FutureProvider<List<Contact>>((ref) {
  return ref.read(contactsRepositoryProvider).listAll();
});
