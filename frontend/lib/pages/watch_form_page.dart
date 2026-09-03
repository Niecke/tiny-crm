import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/task.dart' show recurrenceRules, recurrenceUnits;
import '../models/watch.dart';
import '../providers/organizations_provider.dart';
import '../providers/watches_provider.dart';

const _recurrenceLabels = {
  'daily': 'Daily',
  'weekly': 'Weekly',
  'monthly': 'Monthly',
  'yearly': 'Yearly',
};

/// Create or edit a source to sweep.
class WatchFormPage extends ConsumerStatefulWidget {
  const WatchFormPage({super.key, this.watch, this.initialOrganizationId});

  final Watch? watch;

  /// Pre-links a company, for "watch their careers page" started from an
  /// organization.
  final String? initialOrganizationId;

  @override
  ConsumerState<WatchFormPage> createState() => _WatchFormPageState();
}

class _WatchFormPageState extends ConsumerState<WatchFormPage> {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _name;
  late final TextEditingController _url;
  late final TextEditingController _queryNote;
  late final TextEditingController _notes;
  late final TextEditingController _interval;

  late WatchKind _kind;
  late String _rule;
  late bool _active;
  String? _organizationId;

  bool get _isEdit => widget.watch != null;

  @override
  void initState() {
    super.initState();
    final w = widget.watch;
    _name = TextEditingController(text: w?.name);
    _url = TextEditingController(text: w?.url);
    _queryNote = TextEditingController(text: w?.queryNote);
    _notes = TextEditingController(text: w?.notes);
    _interval = TextEditingController(text: (w?.recurrenceInterval ?? 1).toString());
    // A careers page is the kind that has a company behind it, so opening the
    // form from an organization implies it.
    _kind = w?.kind ??
        (widget.initialOrganizationId != null ? WatchKind.careersPage : WatchKind.jobBoard);
    _rule = w?.recurrenceRule ?? 'weekly';
    _active = w?.active ?? true;
    _organizationId = w?.organizationId ?? widget.initialOrganizationId;
  }

  @override
  void dispose() {
    for (final ctrl in [_name, _url, _queryNote, _notes, _interval]) {
      ctrl.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    String? orNull(TextEditingController ctrl) =>
        ctrl.text.trim().isEmpty ? null : ctrl.text.trim();

    final body = <String, dynamic>{
      'name': _name.text.trim(),
      'url': _url.text.trim(),
      'kind': _kind.wire,
      'query_note': orNull(_queryNote),
      'notes': orNull(_notes),
      // Always sent, including null: that is how a source is unlinked from a
      // company, and PATCH only touches the fields it receives.
      'organization_id': _organizationId,
      'recurrence_rule': _rule,
      'recurrence_interval': int.parse(_interval.text.trim()),
      'active': _active,
    };

    final repo = ref.read(watchesRepositoryProvider);
    try {
      if (_isEdit) {
        await repo.update(widget.watch!.id, body);
      } else {
        await repo.create(body);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not save the source.');
        setState(() => _saving = false);
      }
      return;
    }

    ref.invalidate(watchesProvider);
    ref.invalidate(dueWatchCountProvider);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? 'Edit Source' : 'New Source')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            _field(_name, 'Name', required: true, hint: 'ANKÖ, karriere.at, ORF careers'),
            _field(
              _url,
              'URL',
              required: true,
              hint: 'https://…  — the exact page or saved search to open',
            ),
            _kindPicker(),
            _field(
              _queryNote,
              'What to look for',
              maxLines: 2,
              hint: 'CPV 72000, Wien + NÖ, ab 50k',
              // The URL alone is unreadable six months later.
              helper: 'The saved search in words — keywords, CPV codes, region.',
            ),
            _organizationPicker(),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(flex: 2, child: _rulePicker()),
                const SizedBox(width: 12),
                Expanded(
                  child: _field(
                    _interval,
                    'Every',
                    suffix: recurrenceUnits[_rule],
                    validator: (v) {
                      final n = int.tryParse((v ?? '').trim());
                      if (n == null || n < 1 || n > 366) return '1 to 366';
                      return null;
                    },
                  ),
                ),
              ],
            ),
            SwitchListTile(
              value: _active,
              onChanged: (v) => setState(() => _active = v),
              title: const Text('Active'),
              subtitle: const Text('Pause a source without losing its history'),
              contentPadding: EdgeInsets.zero,
            ),
            const SizedBox(height: 8),
            _field(_notes, 'Notes', maxLines: 3),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving ? const CircularProgressIndicator() : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _kindPicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: DropdownButtonFormField<WatchKind>(
        initialValue: _kind,
        decoration: const InputDecoration(
          labelText: 'Kind',
          border: OutlineInputBorder(),
        ),
        items: [
          for (final kind in WatchKind.values)
            DropdownMenuItem(value: kind, child: Text(kind.label)),
        ],
        onChanged: (v) => setState(() => _kind = v ?? _kind),
      ),
    );
  }

  Widget _rulePicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: DropdownButtonFormField<String>(
        initialValue: _rule,
        decoration: const InputDecoration(
          labelText: 'Check',
          border: OutlineInputBorder(),
        ),
        items: [
          for (final rule in recurrenceRules)
            DropdownMenuItem(value: rule, child: Text(_recurrenceLabels[rule]!)),
        ],
        // The suffix on the interval field counts this rule's unit.
        onChanged: (v) => setState(() => _rule = v ?? _rule),
      ),
    );
  }

  /// Optional on every kind: finding a company you have not filed yet is
  /// normal, and refusing the source until you do is backwards.
  Widget _organizationPicker() {
    final organizationsAsync = ref.watch(allOrganizationsProvider);

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Company (optional)',
          border: OutlineInputBorder(),
          helperText: 'Set for a careers page; leave empty for a board or portal.',
        ),
        child: organizationsAsync.when(
          loading: () => const Text('Loading…'),
          error: (e, _) => Text(errorText(e)),
          data: (organizations) {
            // A stale id (the company was deleted elsewhere) would make the
            // dropdown assert, so fall back to "None".
            final known = organizations.any((o) => o.id == _organizationId);
            return DropdownButtonHideUnderline(
              child: DropdownButton<String?>(
                isExpanded: true,
                value: known ? _organizationId : null,
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('None')),
                  for (final organization in organizations)
                    DropdownMenuItem<String?>(
                      value: organization.id,
                      child: Text(organization.name, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (v) => setState(() => _organizationId = v),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _field(
    TextEditingController ctrl,
    String label, {
    bool required = false,
    String? hint,
    String? helper,
    String? suffix,
    int maxLines = 1,
    String? Function(String?)? validator,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: TextFormField(
        controller: ctrl,
        maxLines: maxLines,
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          helperText: helper,
          suffixText: suffix,
          border: const OutlineInputBorder(),
        ),
        validator: validator ??
            (required ? (v) => (v == null || v.trim().isEmpty) ? '$label is required' : null : null),
      ),
    );
  }
}
