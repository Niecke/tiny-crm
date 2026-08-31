import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/deal.dart';
import '../providers/contacts_provider.dart';
import '../providers/deals_provider.dart';
import '../providers/organizations_provider.dart';

/// Create or edit a deal. Pops with the saved [Deal].
class DealFormPage extends ConsumerStatefulWidget {
  const DealFormPage({
    super.key,
    this.deal,
    this.initialContactId,
    this.initialOrganizationId,
  });

  final Deal? deal;

  /// Pre-selects who the deal is with, for "new deal" started from a customer.
  final String? initialContactId;
  final String? initialOrganizationId;

  @override
  ConsumerState<DealFormPage> createState() => _DealFormPageState();
}

class _DealFormPageState extends ConsumerState<DealFormPage> {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _title;
  late final TextEditingController _fixedValue;
  late final TextEditingController _rate;
  late final TextEditingController _estimatedVolume;
  late final TextEditingController _currency;
  late final TextEditingController _probability;
  late final TextEditingController _lostReason;
  late final TextEditingController _notes;

  late DealValueType _valueType;
  RateUnit? _rateUnit;
  RateUnit? _volumeUnit;
  late DealStage _stage;
  DateTime? _expectedCloseDate;
  String? _contactId;
  String? _organizationId;

  bool get _isEdit => widget.deal != null;
  bool get _isRatePriced => _valueType != DealValueType.fixed;

  @override
  void initState() {
    super.initState();
    final d = widget.deal;
    _title = TextEditingController(text: d?.title);
    _fixedValue = TextEditingController(text: d?.fixedValue);
    _rate = TextEditingController(text: d?.rate);
    _estimatedVolume = TextEditingController(text: d?.estimatedVolume);
    _currency = TextEditingController(text: d?.currency ?? 'EUR');
    _probability = TextEditingController(text: d?.probability?.toString());
    _lostReason = TextEditingController(text: d?.lostReason);
    _notes = TextEditingController(text: d?.notes);
    _valueType = d?.valueType ?? DealValueType.fixed;
    _rateUnit = d?.rateUnit;
    _volumeUnit = d?.volumeUnit;
    _stage = d?.stage ?? DealStage.lead;
    _expectedCloseDate = d?.expectedCloseDate;
    _contactId = d?.contactId ?? widget.initialContactId;
    _organizationId = d?.organizationId ?? widget.initialOrganizationId;
  }

  @override
  void dispose() {
    for (final ctrl in [
      _title,
      _fixedValue,
      _rate,
      _estimatedVolume,
      _currency,
      _probability,
      _lostReason,
      _notes,
    ]) {
      ctrl.dispose();
    }
    super.dispose();
  }

  String _ymd(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  /// A comma is what half of Europe types for a decimal point; the API only
  /// accepts a dot, so translate rather than reject.
  String? _decimal(TextEditingController ctrl) {
    final text = ctrl.text.trim().replaceAll(',', '.');
    return text.isEmpty ? null : text;
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: _expectedCloseDate ?? now,
      firstDate: DateTime(now.year - 5),
      lastDate: DateTime(now.year + 10),
    );
    if (date == null || !mounted) return;
    setState(() => _expectedCloseDate = date);
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    // Empty means "clear this field", not "leave it alone": on an edit the
    // server would otherwise keep a value the user just deleted.
    String? orNull(String text) => text.trim().isEmpty ? null : text.trim();

    final body = <String, dynamic>{
      'title': _title.text.trim(),
      // Every amount is sent as a string, which is how the API sends it back —
      // money never goes through a double. See core/money_text.dart.
      //
      // Only the fields belonging to the chosen shape are sent, and the others
      // are explicitly nulled: the API refuses a deal that claims to be both a
      // fixed bid and a day rate, and on an edit a stale value would otherwise
      // survive the switch.
      'value_type': _valueType.wire,
      'fixed_value': _isRatePriced ? null : _decimal(_fixedValue),
      'rate': _isRatePriced ? _decimal(_rate) : null,
      'rate_unit': _isRatePriced ? _rateUnit?.wire : null,
      // Null here is meaningful: the engagement is genuinely open-ended, and
      // the API reports no total rather than a zero.
      'estimated_volume': _isRatePriced ? _decimal(_estimatedVolume) : null,
      'volume_unit':
          _isRatePriced && _decimal(_estimatedVolume) != null ? _volumeUnit?.wire : null,
      'currency': _currency.text.trim().toUpperCase(),
      'stage': _stage.wire,
      'expected_close_date': _expectedCloseDate == null ? null : _ymd(_expectedCloseDate!),
      'probability': _probability.text.trim().isEmpty
          ? null
          : int.parse(_probability.text.trim()),
      // The API refuses a reason on any stage but "lost", and clears the stored
      // one itself when a deal is won or reopened.
      if (_stage == DealStage.lost) 'lost_reason': orNull(_lostReason.text),
      'notes': orNull(_notes.text),
      'contact_id': _contactId,
      'organization_id': _organizationId,
    };

    final repo = ref.read(dealsRepositoryProvider);
    final Deal saved;
    try {
      if (_isEdit) {
        saved = await repo.update(widget.deal!.id, body);
      } else {
        saved = await repo.create(body);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not save deal.');
        setState(() => _saving = false);
      }
      return;
    }

    ref.invalidate(dealsProvider);
    if (mounted) Navigator.pop(context, saved);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? 'Edit Deal' : 'New Deal')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            _field(_title, 'Title', required: true, hint: 'Website relaunch'),
            ..._valueSection(),
            _stagePicker(),
            // Only while the deal is actually lost — the same rule the API
            // enforces, so the form cannot compose a request it will refuse.
            if (_stage == DealStage.lost)
              _field(_lostReason, 'Lost reason', hint: 'Went with a cheaper agency'),
            _closeDatePicker(),
            _field(
              _probability,
              'Probability (%)',
              validator: _validateProbability,
              // The server pins it once the deal is decided, so offering to
              // edit it here would just be a field that does not stick.
              enabled: _stage.isOpen,
              hint: _stage.isOpen
                  ? null
                  : 'Fixed at ${_stage.isWon ? 100 : 0}% once ${_stage.label.toLowerCase()}',
            ),
            _customerPicker(
              label: 'Contact',
              value: _contactId,
              onChanged: (v) => setState(() => _contactId = v),
              itemsAsync: ref
                  .watch(allContactsProvider)
                  .whenData((contacts) => {for (final c in contacts) c.id: c.name}),
            ),
            _customerPicker(
              label: 'Organization',
              value: _organizationId,
              onChanged: (v) => setState(() => _organizationId = v),
              itemsAsync: ref
                  .watch(allOrganizationsProvider)
                  .whenData((orgs) => {for (final o in orgs) o.id: o.name}),
            ),
            _field(_notes, 'Notes', maxLines: 4),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving ? const CircularProgressIndicator() : const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }

  /// The pricing block, which changes shape with the value type.
  ///
  /// Only one shape's fields are ever on screen, mirroring the server rule that
  /// a deal cannot be both a fixed bid and a day rate — the form can never
  /// compose a request the API will refuse.
  List<Widget> _valueSection() {
    return [
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 2, child: _valueTypePicker()),
          const SizedBox(width: 12),
          Expanded(child: _field(_currency, 'Currency', validator: _validateCurrency)),
        ],
      ),
      if (!_isRatePriced)
        _field(_fixedValue, 'Contract sum', validator: _validateMoney, hint: '12500.00')
      else ...[
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(flex: 2, child: _field(_rate, 'Rate', validator: _validateMoney)),
            const SizedBox(width: 12),
            Expanded(
              child: _unitPicker(
                label: 'per',
                value: _rateUnit,
                onChanged: (unit) => setState(() {
                  _rateUnit = unit;
                  // Default the estimate to the same unit, so the total can
                  // actually be derived — mismatched units derive nothing.
                  _volumeUnit ??= unit;
                }),
              ),
            ),
          ],
        ),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              flex: 2,
              child: _field(
                _estimatedVolume,
                'Estimated volume',
                validator: _validateMoney,
                hint: 'Leave empty if open-ended',
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _unitPicker(
                label: 'unit',
                value: _volumeUnit,
                onChanged: (unit) => setState(() => _volumeUnit = unit),
              ),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Text(_valueHint(), style: Theme.of(context).textTheme.bodySmall),
        ),
      ],
    ];
  }

  /// Says plainly what the deal will be worth, so "no total" never looks like a
  /// mistake the operator made.
  String _valueHint() {
    if (_decimal(_estimatedVolume) == null) {
      return 'No volume estimate — this deal counts as open-ended, and the '
          'pipeline reports it separately rather than as zero.';
    }
    if (_rateUnit != null && _volumeUnit != null && _rateUnit != _volumeUnit) {
      return 'The estimate is in ${_volumeUnit!.plural} but the rate is per '
          '${_rateUnit!.label}, so no total is derived — converting would mean '
          'inventing a ${_rateUnit!.plural}-per-${_volumeUnit!.label} factor.';
    }
    return 'Total is rate × estimated volume.';
  }

  Widget _valueTypePicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Priced as',
          border: OutlineInputBorder(),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<DealValueType>(
            isExpanded: true,
            value: _valueType,
            items: [
              for (final type in DealValueType.values)
                DropdownMenuItem<DealValueType>(value: type, child: Text(type.label)),
            ],
            onChanged: (v) => setState(() {
              _valueType = v ?? _valueType;
              // A retainer is nearly always monthly; a bare rate is usually
              // daily. Only a guess at the starting point — both stay editable.
              if (_isRatePriced) {
                _rateUnit ??=
                    _valueType == DealValueType.retainer ? RateUnit.month : RateUnit.day;
                _volumeUnit ??= _rateUnit;
              }
            }),
          ),
        ),
      ),
    );
  }

  Widget _unitPicker({
    required String label,
    required RateUnit? value,
    required ValueChanged<RateUnit?> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<RateUnit?>(
            isExpanded: true,
            value: value,
            items: [
              const DropdownMenuItem<RateUnit?>(value: null, child: Text('—')),
              for (final unit in RateUnit.values)
                DropdownMenuItem<RateUnit?>(value: unit, child: Text(unit.label)),
            ],
            onChanged: onChanged,
          ),
        ),
      ),
    );
  }

  String? _validateMoney(String? raw) {
    final text = (raw ?? '').trim().replaceAll(',', '.');
    if (text.isEmpty) return null;
    if (!RegExp(r'^\d{1,12}(\.\d{1,2})?$').hasMatch(text)) {
      return 'An amount like 12500.00';
    }
    return null;
  }

  String? _validateCurrency(String? raw) {
    final text = (raw ?? '').trim();
    if (!RegExp(r'^[A-Za-z]{3}$').hasMatch(text)) return 'Three letters, e.g. EUR';
    return null;
  }

  String? _validateProbability(String? raw) {
    final text = (raw ?? '').trim();
    if (text.isEmpty) return null;
    final parsed = int.tryParse(text);
    if (parsed == null || parsed < 0 || parsed > 100) return '0 to 100';
    return null;
  }

  Widget _stagePicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Stage',
          border: OutlineInputBorder(),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<DealStage>(
            isExpanded: true,
            value: _stage,
            items: [
              for (final stage in DealStage.values)
                DropdownMenuItem<DealStage>(value: stage, child: Text(stage.label)),
            ],
            onChanged: (v) => setState(() => _stage = v ?? _stage),
          ),
        ),
      ),
    );
  }

  Widget _closeDatePicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Expected close date',
          border: OutlineInputBorder(),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                _expectedCloseDate == null ? 'No forecast' : _ymd(_expectedCloseDate!),
                style: _expectedCloseDate == null
                    ? const TextStyle(color: Colors.grey)
                    : null,
              ),
            ),
            if (_expectedCloseDate != null)
              IconButton(
                icon: const Icon(Icons.clear),
                tooltip: 'Clear',
                onPressed: () => setState(() => _expectedCloseDate = null),
              ),
            TextButton(onPressed: _pickDate, child: const Text('Pick')),
          ],
        ),
      ),
    );
  }

  /// Contact and organization both pick from the full unpaged list, so a
  /// customer entered long ago is still selectable — same reason the contact
  /// form's organization picker uses allOrganizationsProvider.
  Widget _customerPicker({
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
                    DropdownMenuItem<String?>(value: entry.key, child: Text(entry.value)),
                ],
                onChanged: onChanged,
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
    int maxLines = 1,
    bool enabled = true,
    String? Function(String?)? validator,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: TextFormField(
        controller: ctrl,
        maxLines: maxLines,
        enabled: enabled,
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          border: const OutlineInputBorder(),
        ),
        validator: validator ??
            (required ? (v) => (v == null || v.isEmpty) ? '$label is required' : null : null),
      ),
    );
  }
}
