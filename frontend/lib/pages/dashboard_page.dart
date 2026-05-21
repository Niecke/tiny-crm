import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/contact.dart';
import '../models/task.dart';
import '../providers/contacts_provider.dart';
import '../providers/tasks_provider.dart';
import 'contact_detail_page.dart';
import 'contact_form_page.dart';
import 'task_form_page.dart';

class DashboardPage extends StatelessWidget {
  const DashboardPage({super.key});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 700) {
          return const Padding(
            padding: EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(width: 360, child: _ContactsPanel()),
                SizedBox(width: 16),
                Expanded(child: _TasksPanel()),
              ],
            ),
          );
        }
        return DefaultTabController(
          length: 2,
          child: Column(
            children: [
              Expanded(
                child: TabBarView(
                  children: const [_ContactsPanel(), _TasksPanel()],
                ),
              ),
              const TabBar(
                tabs: [
                  Tab(icon: Icon(Icons.people_outline), text: 'Contacts'),
                  Tab(icon: Icon(Icons.task_outlined), text: 'Tasks'),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ContactsPanel extends ConsumerStatefulWidget {
  const _ContactsPanel();

  @override
  ConsumerState<_ContactsPanel> createState() => _ContactsPanelState();
}

class _ContactsPanelState extends ConsumerState<_ContactsPanel> {
  final _searchController = TextEditingController();
  String _search = '';
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final contactsAsync = ref.watch(contactsProvider(_search));

    return Card(
      margin: EdgeInsets.zero,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Contacts',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
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
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search contacts…',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _search.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _debounce?.cancel();
                          _searchController.clear();
                          setState(() => _search = '');
                        },
                      ),
                isDense: true,
                border: const OutlineInputBorder(),
              ),
              onChanged: (v) {
                _debounce?.cancel();
                _debounce = Timer(const Duration(seconds: 1), () {
                  setState(() => _search = v.trim());
                });
              },
            ),
          ),
          const Divider(height: 1),
          Expanded(
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
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      itemCount: contacts.length,
                      itemBuilder: (context, index) => _ContactTile(
                        contact: contacts[index],
                        onTap: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) =>
                                ContactDetailPage(contact: contacts[index]),
                          ),
                        ),
                        onEdit: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) =>
                                ContactFormPage(contact: contacts[index]),
                          ),
                        ),
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TasksPanel extends ConsumerStatefulWidget {
  const _TasksPanel();

  @override
  ConsumerState<_TasksPanel> createState() => _TasksPanelState();
}

class _TasksPanelState extends ConsumerState<_TasksPanel> {
  final _searchController = TextEditingController();
  String _search = '';
  bool _includeDone = false;
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final filter = (search: _search, includeDone: _includeDone);
    final tasksAsync = ref.watch(tasksProvider(filter));

    return Card(
      margin: EdgeInsets.zero,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Tasks', style: Theme.of(context).textTheme.titleMedium),
                Row(
                  children: [
                    IconButton(
                      onPressed: () =>
                          setState(() => _includeDone = !_includeDone),
                      icon: Icon(
                        _includeDone
                            ? Icons.check_circle
                            : Icons.check_circle_outline,
                        color: _includeDone
                            ? Theme.of(context).colorScheme.primary
                            : null,
                      ),
                      tooltip: _includeDone
                          ? 'Hide done tasks'
                          : 'Show done tasks',
                    ),
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
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search tasks…',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _search.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _debounce?.cancel();
                          _searchController.clear();
                          setState(() => _search = '');
                        },
                      ),
                isDense: true,
                border: const OutlineInputBorder(),
              ),
              onChanged: (v) {
                _debounce?.cancel();
                _debounce = Timer(const Duration(seconds: 1), () {
                  setState(() => _search = v.trim());
                });
              },
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
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
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
        leading: IconButton(
          icon: Icon(
            task.done ? Icons.check_circle : Icons.radio_button_unchecked,
            color: task.done ? Theme.of(context).colorScheme.primary : null,
          ),
          tooltip: task.done ? 'Mark undone' : 'Mark done',
          onPressed: () async {
            await ref.read(tasksRepositoryProvider).update(task.id, {
              'done': !task.done,
            });
            ref.invalidate(tasksProvider);
          },
        ),
        title: Text(
          task.title,
          style: TextStyle(
            color: task.done ? Colors.grey : titleColor,
            fontWeight: FontWeight.w500,
            decoration: task.done ? TextDecoration.lineThrough : null,
          ),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (task.description != null && task.description!.isNotEmpty) ...[
              MarkdownBody(
                data: task.description!,
                shrinkWrap: true,
                styleSheet: MarkdownStyleSheet.fromTheme(
                  Theme.of(context),
                ).copyWith(p: Theme.of(context).textTheme.bodySmall),
              ),
              const Divider(height: 12),
            ],
            if (task.dueDate != null)
              Text(
                'Due ${_formatDue(task.dueDate!)}',
                style: TextStyle(color: titleColor),
              ),
            Text(
              'Priority: ${_priorityLabels[task.priority.clamp(0, 2)]}',
              style: const TextStyle(color: Colors.grey),
            ),
            if (task.tags.isNotEmpty)
              Wrap(
                spacing: 4,
                children: task.tags
                    .map(
                      (t) => Chip(
                        label: Text(t),
                        visualDensity: VisualDensity.compact,
                      ),
                    )
                    .toList(),
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
  const _ContactTile({
    required this.contact,
    required this.onTap,
    required this.onEdit,
  });

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
                    .map(
                      (t) => Chip(
                        label: Text(t),
                        visualDensity: VisualDensity.compact,
                      ),
                    )
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
