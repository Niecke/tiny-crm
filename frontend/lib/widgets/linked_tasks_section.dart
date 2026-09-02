import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/date_time_text.dart';
import '../core/error_text.dart';
import '../models/task.dart';
import '../pages/task_form_page.dart';
import '../providers/tasks_provider.dart';
import 'pagination_bar.dart';

/// "What do I owe this record?" — the open follow-ups about one contact or
/// deal, with a button to add another already attached to it.
///
/// The question tasks-on-projects could not answer, and the reason T14 is a
/// P0: a CRM follow-up is always about someone.
class LinkedTasksSection extends ConsumerStatefulWidget {
  const LinkedTasksSection({
    super.key,
    this.contactId,
    this.dealId,
    this.padding = EdgeInsets.zero,
  });

  /// Exactly one of these is set; it both filters the list and pre-fills the
  /// new task.
  final String? contactId;
  final String? dealId;

  final EdgeInsetsGeometry padding;

  @override
  ConsumerState<LinkedTasksSection> createState() => _LinkedTasksSectionState();
}

class _LinkedTasksSectionState extends ConsumerState<LinkedTasksSection> {
  int _skip = 0;
  bool _includeDone = false;

  Future<void> _newTask() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => TaskFormPage(
          initialContactId: widget.contactId,
          initialDealId: widget.dealId,
        ),
      ),
    );
    // The form invalidates the providers on save; nothing to do here.
  }

  Future<void> _toggleDone(Task task) async {
    try {
      await ref
          .read(tasksRepositoryProvider)
          .update(task.id, {'done': !task.done});
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not update task.');
      }
      return;
    }
    ref.invalidate(tasksProvider);
    ref.invalidate(allTasksProvider);
    ref.invalidate(linkedTasksProvider);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final async = ref.watch(
      linkedTasksProvider((
        contactId: widget.contactId,
        dealId: widget.dealId,
        interactionId: null,
        includeDone: _includeDone,
        skip: _skip,
      )),
    );

    return Padding(
      padding: widget.padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Tasks', style: Theme.of(context).textTheme.labelLarge),
              const Spacer(),
              IconButton(
                icon: Icon(
                  _includeDone ? Icons.visibility : Icons.visibility_off,
                  size: 18,
                ),
                tooltip: _includeDone ? 'Hide done tasks' : 'Show done tasks',
                onPressed: () => setState(() {
                  _includeDone = !_includeDone;
                  // The old offset means nothing once the filter changes.
                  _skip = 0;
                }),
              ),
              TextButton.icon(
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Add'),
                onPressed: _newTask,
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
              style: TextStyle(color: scheme.error),
            ),
            data: (page) => page.items.isEmpty
                ? const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Text(
                      'Nothing outstanding.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  )
                : Column(
                    children: [
                      for (final task in page.items)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                          leading: IconButton(
                            icon: Icon(
                              task.done
                                  ? Icons.check_circle
                                  : Icons.radio_button_unchecked,
                              color: task.done ? scheme.primary : null,
                            ),
                            tooltip: task.done ? 'Mark undone' : 'Mark done',
                            onPressed: () => _toggleDone(task),
                          ),
                          title: Text(
                            task.title,
                            style: TextStyle(
                              color: task.done
                                  ? Colors.grey
                                  : (task.isOverdue ? scheme.error : null),
                              decoration:
                                  task.done ? TextDecoration.lineThrough : null,
                            ),
                          ),
                          subtitle: _subtitle(task) == null
                              ? null
                              : Text(
                                  _subtitle(task)!,
                                  style: TextStyle(
                                    color: task.isOverdue && !task.done
                                        ? scheme.error
                                        : Colors.grey,
                                  ),
                                ),
                          onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => TaskFormPage(task: task),
                            ),
                          ),
                        ),
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

  /// Due date and repeat, minus whatever the surrounding screen already says.
  String? _subtitle(Task task) {
    final parts = [
      if (task.dueDate != null) 'Due ${formatDay(task.dueDate!)}',
      ?task.recurrenceLabel,
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }
}
