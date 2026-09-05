import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/contact.dart';
import '../providers/contacts_provider.dart';
import '../providers/interactions_provider.dart';
import '../widgets/attached_documents_section.dart';
import '../widgets/confirm_dialog.dart';
import '../widgets/interaction_tile.dart';
import '../widgets/linked_tasks_section.dart';
import '../widgets/pagination_bar.dart';
import 'contact_form_page.dart';
import 'interaction_form_page.dart';

class ContactDetailPage extends ConsumerWidget {
  const ContactDetailPage({super.key, required this.contact});

  final Contact contact;

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final confirmed = await confirmDelete(
      context,
      title: 'Delete contact?',
      message: '"${contact.name}" will be permanently deleted.',
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(contactsRepositoryProvider).delete(contact.id);
    } catch (e) {
      if (context.mounted) {
        showErrorSnackBar(context, e, prefix: 'Delete failed.');
      }
      return;
    }
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
          // What this party is, above the contact details: it decides whether
          // the rest of the page is worth reading.
          _RelationshipChips(contact: contact),
          _Field(label: 'Name', value: contact.name),
          if (contact.jobTitle != null)
            _Field(label: 'Job title', value: contact.jobTitle!),
          if (contact.organizationName != null)
            _Field(label: 'Organization', value: contact.organizationName!),
          if (contact.email != null)
            _Field(label: 'Email', value: contact.email!),
          if (contact.emailSecondary != null)
            _Field(label: 'Second email', value: contact.emailSecondary!),
          if (contact.phone != null)
            _Field(label: 'Phone', value: contact.phone!),
          if (contact.phoneSecondary != null)
            _Field(label: 'Second phone', value: contact.phoneSecondary!),
          if (contact.website != null)
            _Field(label: 'Website', value: contact.website!),
          if (contact.postalAddress != null)
            _Field(label: 'Address', value: contact.postalAddress!),
          if (contact.formattedDayRate != null)
            _Field(label: 'Known day rate', value: contact.formattedDayRate!),
          if (contact.source != null)
            _Field(label: 'Source', value: contact.source!.label),
          if (contact.preferredLanguage != null)
            _Field(label: 'Preferred language', value: contact.preferredLanguage!),
          if (contact.birthday != null)
            _Field(label: 'Birthday', value: _ymd(contact.birthday!)),
          if (contact.notes != null)
            _Field(label: 'Notes', value: contact.notes!),
          // What I owe this person, above what has already happened with them.
          LinkedTasksSection(
            contactId: contact.id,
            padding: const EdgeInsets.symmetric(vertical: 8),
          ),
          _InteractionsSection(contact: contact),
          // The NDA, the signed offer — paperwork that is about this person
          // rather than about a project.
          AttachedDocumentsSection(
            contactId: contact.id,
            padding: const EdgeInsets.symmetric(vertical: 8),
          ),
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

String _ymd(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// Status, type and the freelancer answer, at the top where they are read
/// before anything else.
///
/// Status and type are separate chips because they answer different questions —
/// how far along we are, and what this party is to me. "Never asked" is shown
/// rather than left blank: it is the state that produces the next approach, and
/// a blank would read as "no".
class _RelationshipChips extends StatelessWidget {
  const _RelationshipChips({required this.contact});

  final Contact contact;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final answer = contact.freelancerAnswer;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          if (contact.lifecycleStatus != null)
            _Tag(label: contact.lifecycleStatus!.label, color: scheme.primary),
          if (contact.relationType != null)
            _Tag(label: contact.relationType!.label, color: scheme.secondary),
          _Tag(
            label: answer.label,
            color: switch (answer) {
              FreelancerAnswer.yes => Colors.green.shade700,
              // Grey, not red: "they don't" is a fact, not a failure — and red
              // is already the overdue colour everywhere else in the app.
              FreelancerAnswer.no => scheme.onSurfaceVariant,
              // The list worth working through, so it reads as actionable.
              FreelancerAnswer.unknown => scheme.tertiary,
            },
          ),
        ],
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600),
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
              errorText(e),
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
