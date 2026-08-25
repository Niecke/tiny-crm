import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/contact.dart';
import '../models/interaction.dart';
import '../providers/contacts_provider.dart';
import '../providers/interactions_provider.dart';

const kindLabels = {
  'call': 'Call',
  'meeting': 'Meeting',
  'email': 'Mail',
  'note': 'Note',
  'other': 'Other',
};

const kindIcons = {
  'call': Icons.phone_outlined,
  'meeting': Icons.groups_outlined,
  'email': Icons.mail_outline,
  'note': Icons.sticky_note_2_outlined,
  'other': Icons.more_horiz,
};

class InteractionFormPage extends ConsumerStatefulWidget {
  const InteractionFormPage({
    super.key,
    this.interaction,
    this.initialContactId,
  });

  final Interaction? interaction;

  /// Pre-links a contact when logging straight from the contact detail page.
  final String? initialContactId;

  @override
  ConsumerState<InteractionFormPage> createState() =>
      _InteractionFormPageState();
}

class _InteractionFormPageState extends ConsumerState<InteractionFormPage>
    with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _subject;
  late final TextEditingController _notes;
  late final TextEditingController _duration;
  late final TextEditingController _tags;
  late final TabController _notesTabController;
  late DateTime _occurredAt;
  late String _kind;
  late bool _done;
  late List<String> _contactIds;

  bool get _isEdit => widget.interaction != null;

  @override
  void initState() {
    super.initState();
    final i = widget.interaction;
    _subject = TextEditingController(text: i?.subject);
    _notes = TextEditingController(text: i?.notes);
    _duration = TextEditingController(text: i?.durationMinutes?.toString());
    _tags = TextEditingController(text: i?.tags.join(', '));
    _notesTabController = TabController(length: 2, vsync: this);
    _occurredAt = i?.occurredAt.toLocal() ?? DateTime.now();
    _kind = i?.kind ?? 'note';
    // A new entry in the past is something that already happened; one in the
    // future is a plan, so it starts open.
    _done = i?.done ?? !_occurredAt.isAfter(DateTime.now());
    _contactIds = [
      ...?i?.contactIds,
      if (widget.initialContactId != null &&
          !(i?.contactIds.contains(widget.initialContactId) ?? false))
        widget.initialContactId!,
    ];
  }

  @override
  void dispose() {
    _subject.dispose();
    _notes.dispose();
    _duration.dispose();
    _tags.dispose();
    _notesTabController.dispose();
    super.dispose();
  }

  String _formatWhen(DateTime dt) {
    String two(int v) => v.toString().padLeft(2, '0');
    return '${dt.year}-${two(dt.month)}-${two(dt.day)} ${two(dt.hour)}:${two(dt.minute)}';
  }

  Future<void> _pickWhen() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _occurredAt,
      firstDate: DateTime(_occurredAt.year - 5),
      lastDate: DateTime(_occurredAt.year + 5),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_occurredAt),
    );
    if (!mounted) return;
    setState(() {
      _occurredAt = DateTime(
        date.year,
        date.month,
        date.day,
        time?.hour ?? _occurredAt.hour,
        time?.minute ?? _occurredAt.minute,
      );
    });
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    final tags = _tags.text.isEmpty
        ? <String>[]
        : _tags.text
            .split(',')
            .map((t) => t.trim())
            .where((t) => t.isNotEmpty)
            .toList();

    final body = <String, dynamic>{
      'kind': _kind,
      'subject': _subject.text,
      'notes': _notes.text.isEmpty ? null : _notes.text,
      'occurred_at': _occurredAt.toUtc().toIso8601String(),
      'duration_minutes': int.tryParse(_duration.text.trim()),
      'done': _done,
      'tags': tags,
      'contact_ids': _contactIds,
    };

    final repo = ref.read(interactionsRepositoryProvider);
    if (_isEdit) {
      await repo.update(widget.interaction!.id, body);
    } else {
      await repo.create(body);
    }

    ref.invalidate(interactionsProvider);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final contactsAsync = ref.watch(contactsProvider(''));
    final planned = _occurredAt.isAfter(DateTime.now());

    return Scaffold(
      appBar: AppBar(
        title: Text(_isEdit ? 'Edit Interaction' : 'New Interaction'),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: DropdownButtonFormField<String>(
                initialValue: _kind,
                decoration: const InputDecoration(
                  labelText: 'Kind',
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final k in interactionKinds)
                    DropdownMenuItem(
                      value: k,
                      child: Row(
                        children: [
                          Icon(kindIcons[k], size: 18),
                          const SizedBox(width: 8),
                          Text(kindLabels[k]!),
                        ],
                      ),
                    ),
                ],
                onChanged: (v) => setState(() => _kind = v ?? 'note'),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _subject,
                decoration: const InputDecoration(
                  labelText: 'Subject',
                  hintText: 'Kickoff call, follow-up mail, …',
                  border: OutlineInputBorder(),
                ),
                validator: (v) =>
                    (v == null || v.isEmpty) ? 'Subject is required' : null,
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
                      controller: _notesTabController,
                      tabs: const [Tab(text: 'Edit'), Tab(text: 'Preview')],
                      dividerColor: Colors.transparent,
                    ),
                    const Divider(height: 1),
                    SizedBox(
                      height: 180,
                      child: TabBarView(
                        controller: _notesTabController,
                        children: [
                          Padding(
                            padding: const EdgeInsets.all(8),
                            child: TextField(
                              controller: _notes,
                              maxLines: null,
                              expands: true,
                              decoration: const InputDecoration.collapsed(
                                hintText: 'Notes (Markdown supported)',
                              ),
                            ),
                          ),
                          SingleChildScrollView(
                            padding: const EdgeInsets.all(12),
                            child: ListenableBuilder(
                              listenable: _notes,
                              builder: (context, _) {
                                final text = _notes.text;
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
                decoration: InputDecoration(
                  labelText: 'When',
                  helperText: planned
                      ? 'In the future — this is a planned interaction'
                      : 'In the past — this goes into the activity log',
                  border: const OutlineInputBorder(),
                ),
                child: Row(
                  children: [
                    Expanded(child: Text(_formatWhen(_occurredAt))),
                    TextButton(
                      onPressed: _pickWhen,
                      child: const Text('Pick'),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _duration,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Duration (minutes)',
                  border: OutlineInputBorder(),
                ),
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return null;
                  final parsed = int.tryParse(v.trim());
                  if (parsed == null || parsed < 0) return 'Whole minutes only';
                  return null;
                },
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: SwitchListTile(
                value: _done,
                onChanged: (v) => setState(() => _done = v),
                title: const Text('Happened'),
                subtitle: const Text(
                  'Off for planned interactions still to come',
                ),
                contentPadding: EdgeInsets.zero,
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: _ContactPicker(
                contactsAsync: contactsAsync,
                selectedIds: _contactIds,
                onChanged: (ids) => setState(() => _contactIds = ids),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: TextFormField(
                controller: _tags,
                decoration: const InputDecoration(
                  labelText: 'Tags',
                  hintText: 'sales, support, onboarding',
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

class _ContactPicker extends StatelessWidget {
  const _ContactPicker({
    required this.contactsAsync,
    required this.selectedIds,
    required this.onChanged,
  });

  final AsyncValue<List<Contact>> contactsAsync;
  final List<String> selectedIds;
  final ValueChanged<List<String>> onChanged;

  @override
  Widget build(BuildContext context) {
    return contactsAsync.when(
      loading: () => const LinearProgressIndicator(),
      error: (e, _) => Text('Error loading contacts: $e'),
      data: (contacts) {
        final selected =
            contacts.where((c) => selectedIds.contains(c.id)).toList();
        final available =
            contacts.where((c) => !selectedIds.contains(c.id)).toList();

        return InputDecorator(
          decoration: const InputDecoration(
            labelText: 'Contacts',
            border: OutlineInputBorder(),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (selected.isEmpty)
                const Text(
                  'No contact linked yet.',
                  style: TextStyle(color: Colors.grey),
                )
              else
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: [
                    for (final c in selected)
                      InputChip(
                        label: Text(c.name),
                        deleteIcon: const Icon(Icons.close, size: 16),
                        onDeleted: () => onChanged(
                          selectedIds.where((id) => id != c.id).toList(),
                        ),
                        visualDensity: VisualDensity.compact,
                      ),
                  ],
                ),
              if (available.isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Link contact'),
                    onPressed: () async {
                      final picked = await showDialog<Contact>(
                        context: context,
                        builder: (ctx) => SimpleDialog(
                          title: const Text('Link contact'),
                          children: [
                            for (final c in available)
                              SimpleDialogOption(
                                onPressed: () => Navigator.pop(ctx, c),
                                child: Text(c.name),
                              ),
                          ],
                        ),
                      );
                      if (picked == null) return;
                      onChanged([...selectedIds, picked.id]);
                    },
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
