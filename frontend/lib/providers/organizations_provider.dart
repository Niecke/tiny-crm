import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/organization.dart';
import '../models/paged_result.dart';
import '../repositories/organizations_repository.dart';

final organizationsRepositoryProvider = Provider<OrganizationsRepository>((ref) {
  return OrganizationsRepository(dio);
});

typedef OrganizationsFilter = ({String search, int skip});

/// Keyed by search text and page offset — records compare by value, so two
/// widgets asking for the same page share one request. Callers must reset
/// `skip` to 0 whenever `search` changes.
final organizationsProvider =
    FutureProvider.family<PagedResult<Organization>, OrganizationsFilter>((ref, filter) {
  return ref.read(organizationsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        skip: filter.skip,
      );
});

/// Every organization, for the picker on the contact form. Unpaged on purpose —
/// see OrganizationsRepository.listAll.
final allOrganizationsProvider = FutureProvider<List<Organization>>((ref) {
  return ref.read(organizationsRepositoryProvider).listAll();
});
