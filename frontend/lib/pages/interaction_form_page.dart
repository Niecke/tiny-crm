import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/date_time_text.dart';
import '../core/error_text.dart';
import '../models/interaction.dart';
import '../providers/interactions_provider.dart';
import '../widgets/attachment_pickers.dart';

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
    this.initialOrganizationId,
    this.initialDealId,
    this.initialProjectId,
  });

  final Interaction? interaction;

  /// Pre-links the record the form was opened from — logging straight from a
  /// contact, an organization, a deal or a project detail page.
  final String? initialContactId;
  final String? initialOrganizationId;
  final String? initialDealId;
  final String? initialProjectId;

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
  late final TextEditingController _when;
  late String _kind;
  late bool _done;
  late AttachmentLinks _links;

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
    final occurredAt = i?.occurredAt.toLocal() ?? DateTime.now();
    _when = TextEditingController(text: formatWhen(occurredAt));
    _kind = i?.kind ?? 'note';
    // A new entry in the past is something that already happened; one in the
    // future is a plan, so it starts open.
    _done = i?.done ?? !occurredAt.isAfter(DateTime.now());
    _links = (
      contactIds: withInitial(i?.contactIds, widget.initialContactId),
      organizationIds:
          withInitial(i?.organizationIds, widget.initialOrganizationId),
      dealIds: withInitial(i?.dealIds, widget.initialDealId),
      projectIds: withInitial(i?.projectIds, widget.initialProjectId),
    );
  }

  @override
  void dispose() {
    _subject.dispose();
    _notes.dispose();
    _duration.dispose();
    _tags.dispose();
    _when.dispose();
    _notesTabController.dispose();
    super.dispose();
  }

  /// The typed text, or now when it is not (yet) a valid timestamp.
  DateTime get _occurredAt => parseWhen(_when.text) ?? DateTime.now();

  /// The pickers are optional — the field can just be typed into.
  Future<void> _pickWhen() async {
    final current = _occurredAt;
    final date = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(current.year - 5),
      lastDate: DateTime(current.year + 5),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
    );
    if (!mounted) return;
    setState(() {
      _when.text = formatWhen(
        DateTime(
          date.year,
          date.month,
          date.day,
          time?.hour ?? current.hour,
          time?.minute ?? current.minute,
        ),
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
      'occurred_at': parseWhen(_when.text)!.toUtc().toIso8601String(),
      'duration_minutes': int.tryParse(_duration.text.trim()),
      'done': _done,
      'tags': tags,
      // Whole lists: the API replaces what was there, so an emptied picker
      // detaches rather than silently leaving the old link in place.
      'contact_ids': _links.contactIds,
      'organization_ids': _links.organizationIds,
      'deal_ids': _links.dealIds,
      'project_ids': _links.projectIds,
    };

    final repo = ref.read(interactionsRepositoryProvider);
    try {
      if (_isEdit) {
        await repo.update(widget.interaction!.id, body);
      } else {
        await repo.create(body);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not save interaction.');
        setState(() => _saving = false);
      }
      return;
    }

    ref.invalidate(interactionsProvider);
    // The detail screens list interactions attached to their own record.
    ref.invalidate(attachedInteractionsProvider);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final typed = parseWhen(_when.text);
    final planned = typed != null && typed.isAfter(DateTime.now());

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
              child: TextFormField(
                controller: _when,
                decoration: InputDecoration(
                  labelText: 'When',
                  hintText: whenPattern,
                  helperText: planned
                      ? 'In the future — this is a planned interaction'
                      : 'In the past — this goes into the activity log',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.event_outlined),
                    tooltip: 'Pick from calendar',
                    onPressed: _pickWhen,
                  ),
                ),
                // Keeps the planned/logged hint in sync while typing.
                onChanged: (_) => setState(() {}),
                validator: (v) =>
                    parseWhen(v ?? '') == null ? 'Use $whenPattern' : null,
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
            // What it was about. Contacts used to be the only answer, so
            // "every call about this deal" could not be asked.
            AttachmentPickers(
              value: _links,
              onChanged: (v) => setState(() => _links = v),
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
