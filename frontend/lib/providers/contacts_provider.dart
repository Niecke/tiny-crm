import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/contact.dart';
import '../repositories/contacts_repository.dart';

// Provider for the repository — single instance, injected wherever needed.
// ref.read(contactsRepositoryProvider) in callbacks.
final contactsRepositoryProvider = Provider<ContactsRepository>((ref) {
  return ContactsRepository(dio);
});

// FutureProvider for the contacts list.
// Any widget that calls ref.watch(contactsProvider) rebuilds automatically
// when ref.invalidate(contactsProvider) is called from anywhere in the app.
final contactsProvider = FutureProvider<List<Contact>>((ref) {
  return ref.read(contactsRepositoryProvider).list();
});
