import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/contact.dart';
import '../repositories/contacts_repository.dart';

// Provider for the repository — single instance, injected wherever needed.
// ref.read(contactsRepositoryProvider) in callbacks.
final contactsRepositoryProvider = Provider<ContactsRepository>((ref) {
  return ContactsRepository(dio);
});

// FutureProvider.family for the contacts list — keyed by search string.
// Pass empty string to load all. Any widget calling ref.watch(contactsProvider(''))
// rebuilds automatically when ref.invalidate(contactsProvider) is called.
final contactsProvider = FutureProvider.family<List<Contact>, String>((
  ref,
  search,
) {
  return ref
      .read(contactsRepositoryProvider)
      .list(search: search.isEmpty ? null : search);
});
