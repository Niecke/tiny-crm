import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/date_time_text.dart';
import '../core/error_text.dart';
import '../models/interaction.dart';
import '../models/task.dart';
import '../providers/contacts_provider.dart';
import '../providers/deals_provider.dart';
import '../providers/tasks_provider.dart';

const _recurrenceLabels = {
  'daily': 'Daily',
  'weekly': 'Weekly',
  'monthly': 'Monthly',
  'yearly': 'Yearly',
};

class TaskFormPage extends ConsumerStatefulWidget {
  const TaskFormPage({
    super.key,
    this.task,
    this.initialContactId,
    this.initialDealId,
    this.initialInteraction,
  });

  final Task? task;

  /// Pre-fills what the task is about, for "new task" started from a contact
  /// or a deal — the whole point of T14 is that a follow-up is about someone.
  final String? initialContactId;
  final String? initialDealId;

  /// The interaction this task follows up on. Passed whole rather than by id
  /// because there is no interaction picker: you do not choose one out of a
  /// dropdown of a hundred rows called "Call", you say "follow up on this one",
  /// and the form then needs its subject to show what it is attached to.
  final Interaction? initialInteraction;

  @override
  ConsumerState<TaskFormPage> createState() => _TaskFormPageState();
}

class _TaskFormPageState extends ConsumerState<TaskFormPage>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _title;
  late final TextEditingController _description;
  late final TextEditingController _tags;
  late final TextEditingController _recurrenceInterval;
  late final TabController _descTabController;
  DateTime? _dueDate;
  int _priority = 0;
  String? _recurrenceRule;
  DateTime? _recurrenceUntil;

  // What the task is about.
  String? _contactId;
  String? _dealId;
  String? _interactionId;

  /// Subject of the linked interaction, for the read-only row. Comes either
  /// from the task being edited or from the tile the form was opened from.
  String? _interactionSubject;

  bool get _isEdit => widget.task != null;

  @override
  void initState() {
    super.initState();
    final t = widget.task;
    _contactId = t?.contactId ?? widget.initialContactId;
    _dealId = t?.dealId ?? widget.initialDealId;
    _interactionId = t?.interactionId ?? widget.initialInteraction?.id;
    _interactionSubject =
        t?.interactionSubject ?? widget.initialInteraction?.subject;
    _title = TextEditingController(text: t?.title);
    _description = TextEditingController(text: t?.description);
    _tags = TextEditingController(text: t?.tags.join(', '));
    _recurrenceInterval = TextEditingController(
      text: (t?.recurrenceInterval ?? 1).toString(),
    );
    _descTabController = TabController(length: 2, vsync: this);
    _dueDate = t?.dueDate;
    _priority = t?.priority ?? 0;
    _recurrenceRule = t?.recurrenceRule;
    _recurrenceUntil = t?.recurrenceUntil;
  }

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    _tags.dispose();
    _recurrenceInterval.dispose();
    _descTabController.dispose();
    super.dispose();
  }

  Future<DateTime?> _pickDay(DateTime? current) async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: current ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 5),
    );
    // End-of-day so a task stays "today" until midnight.
    return date == null
        ? null
        : DateTime(date.year, date.month, date.day, 23, 59);
  }

  Future<void> _pickDueDate() async {
    final picked = await _pickDay(_dueDate);
    if (picked == null || !mounted) return;
    setState(() => _dueDate = picked);
  }

  Future<void> _pickRecurrenceUntil() async {
    final picked = await _pickDay(_recurrenceUntil ?? _dueDate);
    if (picked == null || !mounted) return;
    setState(() => _recurrenceUntil = picked);
  }

  /// The noun the interval counts: "Every 2 [weeks]".
  String get _recurrenceUnitLabel => recurrenceUnits[_recurrenceRule] ?? '';

  void _complain(String message) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    // The server enforces both of these too; catching them here keeps the user
    // from losing a form to a round trip.
    if (_recurrenceRule != null && _dueDate == null) {
      _complain('A repeating task needs a due date to repeat from.');
      return;
    }
    if (_recurrenceUntil != null &&
        _dueDate != null &&
        _recurrenceUntil!.isBefore(_dueDate!)) {
      _complain('The repeat end date is before the due date.');
      return;
    }
    setState(() => _saving = true);

    final tags = _tags.text.isEmpty
        ? <String>[]
        : _tags.text.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();

    final body = {
      'title': _title.text,
      if (_description.text.isNotEmpty) 'description': _description.text,
      'due_date': _dueDate?.toUtc().toIso8601String(),
      'priority': _priority,
      'tags': tags,
      // Sent even when null: on a PATCH that is how a repeat gets turned off.
      'recurrence_rule': _recurrenceRule,
      'recurrence_interval':
          _recurrenceRule == null ? 1 : int.parse(_recurrenceInterval.text),
      'recurrence_until': _recurrenceRule == null
          ? null
          : _recurrenceUntil?.toUtc().toIso8601String(),
      // Always sent, including null: that is how a task gets detached from a
      // contact, and PATCH only touches the fields it receives.
      'contact_id': _contactId,
      'deal_id': _dealId,
      'interaction_id': _interactionId,
    };

    final repo = ref.read(tasksRepositoryProvider);
    try {
      if (_isEdit) {
        await repo.update(widget.task!.id, body);
      } else {
        await repo.create(body);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not save task.');
        setState(() => _saving = false);
      }
      return;
    }

    ref.invalidate(tasksProvider);
    ref.invalidate(allTasksProvider);
    // The contact and deal detail screens list their own tasks.
    ref.invalidate(linkedTasksProvider);
    if (mounted) Navigator.pop(context);
  }

  /// What the task is about: a contact, a deal, and the interaction it came
  /// out of. All three independent and all optional — a plain to-do links to
  /// nothing, so none of these is required.
  List<Widget> _linkSection() {
    return [
      _linkPicker(
        label: 'About contact',
        value: _contactId,
        onChanged: (v) => setState(() => _contactId = v),
        itemsAsync: ref
            .watch(allContactsProvider)
            .whenData((contacts) => {for (final c in contacts) c.id: c.name}),
      ),
      _linkPicker(
        label: 'About deal',
        value: _dealId,
        onChanged: (v) => setState(() => _dealId = v),
        itemsAsync: ref
            .watch(allDealsProvider)
            .whenData((deals) => {for (final d in deals) d.id: d.title}),
      ),
      // Read-only: the link is set by "Follow up" on an interaction, not by
      // picking one out of a list of near-identical subjects. Clearable, so an
      // edit can detach it.
      if (_interactionId != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: InputDecorator(
            decoration: const InputDecoration(
              labelText: 'Following up on',
              border: OutlineInputBorder(),
            ),
            child: Row(
              children: [
                Expanded(child: Text(_interactionSubject ?? 'An interaction')),
                IconButton(
                  icon: const Icon(Icons.clear),
                  tooltip: 'Detach',
                  onPressed: () => setState(() {
                    _interactionId = null;
                    _interactionSubject = null;
                  }),
                ),
              ],
            ),
          ),
        ),
    ];
  }

  /// A dropdown over the full unpaged list, so a record entered long ago is
  /// still selectable — same reason the contact form's organization picker
  /// uses allOrganizationsProvider.
  Widget _linkPicker({
    required String label,
    required String? value,
    required ValueChanged<String?> onChanged,
    required AsyncValue<Map<String, String>> itemsAsync,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
        child: itemsAsync.when(
          loading: () => const Text('Loading…'),
          error: (e, _) => Text(errorText(e)),
          data: (items) {
            // A stale id (the record was deleted elsewhere) would make the
            // dropdown assert, so fall back to "None".
            final selected = items.containsKey(value) ? value : null;
            return DropdownButtonHideUnderline(
              child: DropdownButton<String?>(
                isExpanded: true,
                value: selected,
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('None')),
                  for (final entry in items.entries)
                    DropdownMenuItem<String?>(
                      value: entry.key,
                      child: Text(entry.value, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: onChanged,
              ),
            );
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? 'Edit Task' : 'New Task')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _title,
                decoration: const InputDecoration(
                  labelText: 'Title',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.isEmpty) ? 'Title is required' : null,
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: InputDecorator(
                decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  contentPadding: EdgeInsets.zero,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TabBar(
                      controller: _descTabController,
                      tabs: const [Tab(text: 'Edit'), Tab(text: 'Preview')],
                      dividerColor: Colors.transparent,
                    ),
                    const Divider(height: 1),
                    SizedBox(
                      height: 180,
                      child: TabBarView(
                        controller: _descTabController,
                        children: [
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: TextField(
                              controller: _description,
                              maxLines: null,
                              expands: true,
                              decoration: const InputDecoration.collapsed(
                                hintText: 'Description (Markdown supported)',
                              ),
                            ),
                          ),
                          SingleChildScrollView(
                            padding: const EdgeInsets.all(12),
                            child: ListenableBuilder(
                              listenable: _description,
                              builder: (context, _) {
                                final text = _description.text;
                                return text.isEmpty
                                    ? const Text(
                                        'Nothing to preview.',
                                        style: TextStyle(color: Colors.grey),
                                      )
                                    : MarkdownBody(data: text);
                              },
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'Due date',
                  border: OutlineInputBorder(),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _dueDate == null ? 'No due date' : formatDay(_dueDate!),
                      ),
                    ),
                    if (_dueDate != null)
                      IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () => setState(() => _dueDate = null),
                      ),
                    TextButton(
                      onPressed: _pickDueDate,
                      child: const Text('Pick'),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: DropdownButtonFormField<String?>(
                initialValue: _recurrenceRule,
                decoration: const InputDecoration(
                  labelText: 'Repeats',
                  helperText: 'Completing a repeating task creates the next one.',
                  border: OutlineInputBorder(),
                ),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('Does not repeat'),
                  ),
                  for (final rule in recurrenceRules)
                    DropdownMenuItem<String?>(
                      value: rule,
                      child: Text(_recurrenceLabels[rule]!),
                    ),
                ],
                onChanged: (v) => setState(() {
                  _recurrenceRule = v;
                  // An end date without a rule means nothing; drop it with the rule.
                  if (v == null) _recurrenceUntil = null;
                }),
              ),
            ),
            if (_recurrenceRule != null) ...[
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: TextFormField(
                  controller: _recurrenceInterval,
                  keyboardType: TextInputType.number,
                  decoration: InputDecoration(
                    labelText: 'Every',
                    suffixText: _recurrenceUnitLabel,
                    border: const OutlineInputBorder(),
                  ),
                  validator: (v) {
                    final n = int.tryParse((v ?? '').trim());
                    if (n == null || n < 1 || n > 366) {
                      return 'Enter a whole number between 1 and 366';
                    }
                    return null;
                  },
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: InputDecorator(
                  decoration: const InputDecoration(
                    labelText: 'Repeat until',
                    border: OutlineInputBorder(),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          _recurrenceUntil == null
                              ? 'No end date'
                              : formatDay(_recurrenceUntil!),
                        ),
                      ),
                      if (_recurrenceUntil != null)
                        IconButton(
                          icon: const Icon(Icons.clear),
                          onPressed: () =>
                              setState(() => _recurrenceUntil = null),
                        ),
                      TextButton(
                        onPressed: _pickRecurrenceUntil,
                        child: const Text('Pick'),
                      ),
                    ],
                  ),
                ),
              ),
            ],
            ..._linkSection(),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: DropdownButtonFormField<int>(
                initialValue: _priority,
                decoration: const InputDecoration(
                  labelText: 'Priority',
                  border: OutlineInputBorder(),
                ),
                items: const [
                  DropdownMenuItem(value: 0, child: Text('Low')),
                  DropdownMenuItem(value: 1, child: Text('Medium')),
                  DropdownMenuItem(value: 2, child: Text('High')),
                ],
                onChanged: (v) => setState(() => _priority = v ?? 0),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _tags,
                decoration: const InputDecoration(
                  labelText: 'Tags',
                  hintText: 'bug, urgent, feature',
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const CircularProgressIndicator()
                  : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }
}
