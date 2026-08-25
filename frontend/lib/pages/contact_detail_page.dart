import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/contact.dart';
import '../providers/contacts_provider.dart';
import '../providers/interactions_provider.dart';
import '../widgets/interaction_tile.dart';
import '../widgets/pagination_bar.dart';
import 'contact_form_page.dart';
import 'interaction_form_page.dart';

class ContactDetailPage extends ConsumerWidget {
  const ContactDetailPage({super.key, required this.contact});

  final Contact contact;

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete contact'),
        content: Text('Delete "${contact.name}"? This cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;
    await ref.read(contactsRepositoryProvider).delete(contact.id);
    // Invalidate → contactsProvider refetches → ContactsPage list updates automatically
    ref.invalidate(contactsProvider);
    ref.invalidate(allContactsProvider);
    if (context.mounted) Navigator.pop(context);
  }

  Future<void> _edit(BuildContext context, WidgetRef ref) async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => ContactFormPage(contact: contact)),
    );
    // Form already invalidated the provider — pop detail so user lands on fresh list
    if (context.mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: Text(contact.name),
        actions: [
          IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: 'Delete',
            onPressed: () => _delete(context, ref),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          _Field(label: 'Name', value: contact.name),
          if (contact.company != null)
            _Field(label: 'Company', value: contact.company!),
          if (contact.email != null)
            _Field(label: 'Email', value: contact.email!),
          if (contact.phone != null)
            _Field(label: 'Phone', value: contact.phone!),
          if (contact.address != null)
            _Field(label: 'Address', value: contact.address!),
          if (contact.notes != null)
            _Field(label: 'Notes', value: contact.notes!),
          _InteractionsSection(contact: contact),
          if (contact.tags.isNotEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Tags', style: Theme.of(context).textTheme.labelLarge),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 6,
                    children: contact.tags
                        .map((t) => Chip(label: Text(t)))
                        .toList(),
                  ),
                ],
              ),
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _edit(context, ref),
        icon: const Icon(Icons.edit),
        label: const Text('Edit'),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 2),
          SelectableText(value, style: Theme.of(context).textTheme.bodyLarge),
          const Divider(),
        ],
      ),
    );
  }
}


/// Everything logged or planned with this contact, newest first.
class _InteractionsSection extends ConsumerStatefulWidget {
  const _InteractionsSection({required this.contact});

  final Contact contact;

  @override
  ConsumerState<_InteractionsSection> createState() =>
      _InteractionsSectionState();
}

class _InteractionsSectionState extends ConsumerState<_InteractionsSection> {
  int _skip = 0;

  @override
  Widget build(BuildContext context) {
    final contact = widget.contact;
    final async = ref.watch(
      interactionsProvider((
        search: '',
        contactId: contact.id,
        kind: null,
        upcoming: null,
        skip: _skip,
      )),
    );

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                'Interactions',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const Spacer(),
              TextButton.icon(
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Log'),
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) =>
                        InteractionFormPage(initialContactId: contact.id),
                  ),
                ),
              ),
            ],
          ),
          async.when(
            loading: () => const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: LinearProgressIndicator(),
            ),
            error: (e, _) => Text(
              'Error: $e',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
            data: (page) => page.items.isEmpty
                ? const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      'Nothing logged yet.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  )
                : Column(
                    children: [
                      for (final i in page.items)
                        InteractionTile(interaction: i),
                      PaginationBar(
                        page: page,
                        onSkipChanged: (skip) => setState(() => _skip = skip),
                      ),
                    ],
                  ),
          ),
          const Divider(),
        ],
      ),
    );
  }
}
