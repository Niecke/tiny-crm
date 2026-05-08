import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/contact.dart';
import '../models/task.dart';
import '../providers/contacts_provider.dart';
import '../providers/tasks_provider.dart';
import 'contact_detail_page.dart';
import 'contact_form_page.dart';
import 'task_form_page.dart';

// ConsumerWidget = StatelessWidget with access to `ref` (the Riverpod handle).
// ref.watch(provider) → reactive: widget rebuilds when provider value changes.
// ref.read(provider)  → one-shot: use inside callbacks, not in build().
class ContactsPage extends ConsumerWidget {
  const ContactsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // watch rebuilds this widget whenever contactsProvider emits a new value
    final contactsAsync = ref.watch(contactsProvider);

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 360,
            child: Card(
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Contacts', style: Theme.of(context).textTheme.titleMedium),
                        IconButton(
                          onPressed: () => Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const ContactFormPage()),
                          ),
                          icon: const Icon(Icons.add),
                          tooltip: 'New Contact',
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1),
                  Expanded(
                    // .when() is Riverpod's replacement for FutureBuilder — handles
                    // loading / error / data in one clean expression
                    child: contactsAsync.when(
                      loading: () => const Center(child: CircularProgressIndicator()),
                      error: (e, _) => Center(
                        child: SelectableText(
                          'Error: $e',
                          style: TextStyle(color: Theme.of(context).colorScheme.error),
                        ),
                      ),
                      data: (contacts) => contacts.isEmpty
                          ? const Center(child: Text('No contacts yet.'))
                          : ListView.builder(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              itemCount: contacts.length,
                              itemBuilder: (context, index) => _ContactTile(
                                contact: contacts[index],
                                onTap: () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => ContactDetailPage(contact: contacts[index]),
                                  ),
                                ),
                                onEdit: () => Navigator.push(
                                  context,
                                  MaterialPageRoute(
                                    builder: (_) => ContactFormPage(contact: contacts[index]),
                                  ),
                                ),
                              ),
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 16),
          const Expanded(child: _TasksPanel()),
        ],
      ),
    );
  }
}

class _TasksPanel extends ConsumerWidget {
  const _TasksPanel();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tasksAsync = ref.watch(tasksProvider);

    return Card(
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Tasks', style: Theme.of(context).textTheme.titleMedium),
                IconButton(
                  onPressed: () => Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const TaskFormPage()),
                  ),
                  icon: const Icon(Icons.add),
                  tooltip: 'New Task',
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: tasksAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(
                child: SelectableText(
                  'Error: $e',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
              data: (tasks) => tasks.isEmpty
                  ? const Center(child: Text('No tasks yet.'))
                  : ListView.builder(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      itemCount: tasks.length,
                      itemBuilder: (context, index) =>
                          _TaskTile(task: tasks[index]),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TaskTile extends ConsumerWidget {
  const _TaskTile({required this.task});

  final Task task;

  static const _priorityLabels = ['Low', 'Med', 'High'];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overdue = task.isOverdue;
    final titleColor = overdue ? Theme.of(context).colorScheme.error : null;

    return Card(
      margin: const EdgeInsets.only(bottom: 4),
      child: ListTile(
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => TaskFormPage(task: task)),
        ),
        title: Text(
          task.title,
          style: TextStyle(color: titleColor, fontWeight: FontWeight.w500),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (task.dueDate != null)
              Text(
                'Due ${_formatDue(task.dueDate!)}',
                style: TextStyle(color: titleColor),
              ),
            Text(
              'Priority: ${_priorityLabels[task.priority.clamp(0, 2)]}',
              style: const TextStyle(color: Colors.grey),
            ),
          ],
        ),
        trailing: IconButton(
          icon: const Icon(Icons.delete_outline),
          tooltip: 'Delete',
          onPressed: () async {
            await ref.read(tasksRepositoryProvider).delete(task.id);
            ref.invalidate(tasksProvider);
          },
        ),
      ),
    );
  }

  String _formatDue(DateTime dt) {
    final local = dt.toLocal();
    final y = local.year.toString().padLeft(4, '0');
    final m = local.month.toString().padLeft(2, '0');
    final d = local.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }
}

class _ContactTile extends StatelessWidget {
  const _ContactTile({required this.contact, required this.onTap, required this.onEdit});

  final Contact contact;
  final VoidCallback onTap;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 4),
      child: ListTile(
        onTap: onTap,
        title: Text(contact.name),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (contact.company != null) Text(contact.company!),
            if (contact.email != null)
              Text(contact.email!, style: const TextStyle(color: Colors.grey)),
            if (contact.tags.isNotEmpty)
              Wrap(
                spacing: 4,
                children: contact.tags
                    .map((t) => Chip(label: Text(t), visualDensity: VisualDensity.compact))
                    .toList(),
              ),
          ],
        ),
        isThreeLine: true,
        trailing: IconButton(
          icon: const Icon(Icons.edit_outlined),
          tooltip: 'Edit',
          onPressed: onEdit,
        ),
      ),
    );
  }
}
