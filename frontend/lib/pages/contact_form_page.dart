import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/contact.dart';
import '../models/organization.dart';
import '../providers/contacts_provider.dart';
import '../providers/organizations_provider.dart';
import 'organization_form_page.dart';

// ConsumerStatefulWidget = StatefulWidget with ref.
// Use when you need both local mutable state (form controllers) and providers.
class ContactFormPage extends ConsumerStatefulWidget {
  const ContactFormPage({super.key, this.contact, this.initialOrganizationId});

  final Contact? contact;

  /// Pre-selects a company, for "add someone here" from an organization.
  final String? initialOrganizationId;

  @override
  ConsumerState<ContactFormPage> createState() => _ContactFormPageState();
}

class _ContactFormPageState extends ConsumerState<ContactFormPage> {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _name;
  late final TextEditingController _jobTitle;
  late final TextEditingController _email;
  late final TextEditingController _emailSecondary;
  late final TextEditingController _phone;
  late final TextEditingController _phoneSecondary;
  late final TextEditingController _website;
  late final TextEditingController _street;
  late final TextEditingController _postalCode;
  late final TextEditingController _city;
  late final TextEditingController _country;
  late final TextEditingController _preferredLanguage;
  late final TextEditingController _knownDayRate;
  late final TextEditingController _rateCurrency;
  late final TextEditingController _tags;
  late final TextEditingController _notes;

  /// The linked company, or null for someone unaffiliated. Not a text field
  /// any more: free text made "ACME" and "Acme" two different companies.
  String? _organizationId;

  LifecycleStatus? _lifecycleStatus;
  RelationType? _relationType;
  ContactSource? _source;

  /// Tri-state, and it starts at [FreelancerAnswer.unknown] rather than "no":
  /// nobody has been asked yet, and that is a different answer.
  late FreelancerAnswer _worksWithFreelancers;
  DateTime? _birthday;

  bool get _isEdit => widget.contact != null;

  List<TextEditingController> get _controllers => [
        _name,
        _jobTitle,
        _email,
        _emailSecondary,
        _phone,
        _phoneSecondary,
        _website,
        _street,
        _postalCode,
        _city,
        _country,
        _preferredLanguage,
        _knownDayRate,
        _rateCurrency,
        _tags,
        _notes,
      ];

  @override
  void initState() {
    super.initState();
    final c = widget.contact;
    _name = TextEditingController(text: c?.name);
    _jobTitle = TextEditingController(text: c?.jobTitle);
    _email = TextEditingController(text: c?.email);
    _emailSecondary = TextEditingController(text: c?.emailSecondary);
    _phone = TextEditingController(text: c?.phone);
    _phoneSecondary = TextEditingController(text: c?.phoneSecondary);
    _website = TextEditingController(text: c?.website);
    _street = TextEditingController(text: c?.street);
    _postalCode = TextEditingController(text: c?.postalCode);
    _city = TextEditingController(text: c?.city);
    _country = TextEditingController(text: c?.country);
    _preferredLanguage = TextEditingController(text: c?.preferredLanguage);
    _knownDayRate = TextEditingController(text: c?.knownDayRate);
    // Prefilled so the pair is complete by default — the API refuses a rate
    // with no currency, and making the operator type "EUR" every time would be
    // a trap rather than a rule.
    _rateCurrency = TextEditingController(text: c?.rateCurrency ?? 'EUR');
    _tags = TextEditingController(text: c?.tags.join(', '));
    _notes = TextEditingController(text: c?.notes);
    _organizationId = c?.organizationId ?? widget.initialOrganizationId;
    _lifecycleStatus = c?.lifecycleStatus;
    _relationType = c?.relationType;
    _source = c?.source;
    _worksWithFreelancers = FreelancerAnswer.fromBool(c?.worksWithFreelancers);
    _birthday = c?.birthday;
  }

  @override
  void dispose() {
    for (final ctrl in _controllers) {
      ctrl.dispose();
    }
    super.dispose();
  }

  String _ymd(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _pickBirthday() async {
    final now = DateTime.now();
    final date = await showDatePicker(
      context: context,
      initialDate: _birthday ?? DateTime(now.year - 40, now.month, now.day),
      firstDate: DateTime(1900),
      // A birthday in the future is a typo, not a date.
      lastDate: now,
    );
    if (date == null || !mounted) return;
    setState(() => _birthday = date);
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    final tags = _tags.text.isEmpty
        ? <String>[]
        : _tags.text.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();

    // Empty means "clear this field", not "leave it alone": on an edit the
    // server would otherwise keep a value the user just deleted.
    String? orNull(TextEditingController ctrl) =>
        ctrl.text.trim().isEmpty ? null : ctrl.text.trim();

    // A comma is what half of Europe types for a decimal point; the API only
    // accepts a dot, so translate rather than reject.
    final rate = _knownDayRate.text.trim().replaceAll(',', '.');

    final body = <String, dynamic>{
      'name': _name.text.trim(),
      'job_title': orNull(_jobTitle),
      // Always sent, including null: that is how a contact is unlinked from a
      // company, and PATCH only touches the fields it receives.
      'organization_id': _organizationId,
      'email': orNull(_email),
      'email_secondary': orNull(_emailSecondary),
      'phone': orNull(_phone),
      'phone_secondary': orNull(_phoneSecondary),
      'website': orNull(_website),
      'street': orNull(_street),
      'postal_code': orNull(_postalCode),
      'city': orNull(_city),
      'country': orNull(_country),
      'lifecycle_status': _lifecycleStatus?.wire,
      'relation_type': _relationType?.wire,
      'source': _source?.wire,
      'preferred_language': orNull(_preferredLanguage),
      'birthday': _birthday == null ? null : _ymd(_birthday!),
      // The pair goes together or not at all — the API refuses half of it, so
      // the form never composes a request it will refuse. Money is sent as a
      // string, which is how the API sends it back: see core/money_text.dart.
      'known_day_rate': rate.isEmpty ? null : rate,
      'rate_currency': rate.isEmpty ? null : _rateCurrency.text.trim().toUpperCase(),
      // Null for "never asked" — not the same answer as false.
      'works_with_freelancers': _worksWithFreelancers.asBool,
      'tags': tags,
      'notes': orNull(_notes),
    };

    final repo = ref.read(contactsRepositoryProvider);
    try {
      if (_isEdit) {
        await repo.update(widget.contact!.id, body);
      } else {
        await repo.create(body);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not save contact.');
        setState(() => _saving = false);
      }
      return;
    }

    // Invalidate here — every watcher of contactsProvider refetches automatically
    ref.invalidate(contactsProvider);
    ref.invalidate(allContactsProvider);
    // The contact count on the organization list moved with this save.
    ref.invalidate(organizationsProvider);

    if (mounted) Navigator.pop(context);
  }

  Future<void> _createOrganization() async {
    final created = await Navigator.push<Organization>(
      context,
      MaterialPageRoute(builder: (_) => const OrganizationFormPage()),
    );
    if (created == null) return;
    setState(() => _organizationId = created.id);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_isEdit ? 'Edit Contact' : 'New Contact')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            _field(_name, 'Name', required: true),
            _field(_jobTitle, 'Job title', hint: 'Head of Delivery'),
            _organizationPicker(),
            _field(_email, 'Email'),
            _field(_emailSecondary, 'Second email', hint: 'The one that gets answered'),
            _field(_phone, 'Phone'),
            _field(_phoneSecondary, 'Second phone', hint: 'Mobile, direct line'),
            _field(_website, 'Website'),

            // Four fields rather than one blob, so this can feed a letter, an
            // invoice or a vCard without anyone guessing where the parts are.
            _sectionHeader('Address'),
            _field(_street, 'Street', hint: 'Hauptstraße 1'),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: _field(_postalCode, 'Postcode')),
                const SizedBox(width: 12),
                Expanded(flex: 2, child: _field(_city, 'City')),
              ],
            ),
            _field(
              _country,
              'Country',
              hint: 'AT',
              validator: _validateCountry,
            ),

            _sectionHeader('Relationship'),
            // Two dropdowns, not one: status is how far along we are, type is
            // what this party is to me. Collapsing them would lose "partner we
            // have not approached yet".
            _enumPicker<LifecycleStatus>(
              label: 'Status',
              value: _lifecycleStatus,
              values: LifecycleStatus.values,
              labelOf: (v) => v.label,
              onChanged: (v) => setState(() => _lifecycleStatus = v),
            ),
            _enumPicker<RelationType>(
              label: 'Type',
              value: _relationType,
              values: RelationType.values,
              labelOf: (v) => v.label,
              onChanged: (v) => setState(() => _relationType = v),
            ),
            _enumPicker<ContactSource>(
              label: 'Source',
              value: _source,
              values: ContactSource.values,
              labelOf: (v) => v.label,
              onChanged: (v) => setState(() => _source = v),
            ),
            _freelancerPicker(),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  flex: 2,
                  child: _field(
                    _knownDayRate,
                    'Known day rate',
                    hint: 'As heard, not a quote',
                    validator: _validateMoney,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _field(_rateCurrency, 'Currency', validator: _validateRateCurrency),
                ),
              ],
            ),
            _field(
              _preferredLanguage,
              'Preferred language',
              hint: 'de',
              validator: _validateLanguage,
            ),
            _birthdayPicker(),

            _sectionHeader('Filing'),
            _field(_tags, 'Tags', hint: 'vip, prospect, partner'),
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

  Widget _sectionHeader(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Text(text, style: Theme.of(context).textTheme.titleSmall),
    );
  }

  Widget _organizationPicker() {
    final organizationsAsync = ref.watch(allOrganizationsProvider);

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: organizationsAsync.when(
              loading: () => const _PickerShell(child: Text('Loading…')),
              error: (e, _) => _PickerShell(child: Text(errorText(e))),
              data: (organizations) {
                // A stale id (the company was deleted elsewhere) would make the
                // dropdown assert, so fall back to "None".
                final known = organizations.any((o) => o.id == _organizationId);
                final value = known ? _organizationId : null;
                return _PickerShell(
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String?>(
                      isExpanded: true,
                      value: value,
                      items: [
                        const DropdownMenuItem<String?>(
                          value: null,
                          child: Text('None'),
                        ),
                        for (final organization in organizations)
                          DropdownMenuItem<String?>(
                            value: organization.id,
                            child: Text(organization.name),
                          ),
                      ],
                      onChanged: (v) => setState(() => _organizationId = v),
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            icon: const Icon(Icons.add_business_outlined),
            tooltip: 'New organization',
            onPressed: _createOrganization,
          ),
        ],
      ),
    );
  }

  /// One dropdown for any of the nullable classification enums. "Not set" is a
  /// real value on all of them — a business card says none of this.
  Widget _enumPicker<T extends Enum>({
    required String label,
    required T? value,
    required List<T> values,
    required String Function(T) labelOf,
    required ValueChanged<T?> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<T?>(
            isExpanded: true,
            value: value,
            items: [
              DropdownMenuItem<T?>(value: null, child: const Text('Not set')),
              for (final option in values)
                DropdownMenuItem<T?>(value: option, child: Text(labelOf(option))),
            ],
            onChanged: onChanged,
          ),
        ),
      ),
    );
  }

  /// The one question that decides whether an approach is worth making, and the
  /// reason the column is nullable: "never asked" is offered as an answer.
  Widget _freelancerPicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Works with freelancers?',
          border: OutlineInputBorder(),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<FreelancerAnswer>(
            isExpanded: true,
            value: _worksWithFreelancers,
            items: [
              for (final answer in FreelancerAnswer.values)
                DropdownMenuItem<FreelancerAnswer>(
                  value: answer,
                  child: Text(answer.label),
                ),
            ],
            onChanged: (v) => setState(() => _worksWithFreelancers = v ?? _worksWithFreelancers),
          ),
        ),
      ),
    );
  }

  Widget _birthdayPicker() {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Birthday',
          border: OutlineInputBorder(),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                _birthday == null ? 'Not known' : _ymd(_birthday!),
                style: _birthday == null ? const TextStyle(color: Colors.grey) : null,
              ),
            ),
            if (_birthday != null)
              IconButton(
                icon: const Icon(Icons.clear),
                tooltip: 'Clear',
                onPressed: () => setState(() => _birthday = null),
              ),
            TextButton(onPressed: _pickBirthday, child: const Text('Pick')),
          ],
        ),
      ),
    );
  }

  String? _validateMoney(String? raw) {
    final text = (raw ?? '').trim().replaceAll(',', '.');
    if (text.isEmpty) return null;
    if (!RegExp(r'^\d{1,12}(\.\d{1,2})?$').hasMatch(text)) {
      return 'An amount like 850.00';
    }
    return null;
  }

  /// Only demanded once there is a rate to attach it to — the same pairing the
  /// API enforces, so the form cannot compose a request it will refuse.
  String? _validateRateCurrency(String? raw) {
    if (_knownDayRate.text.trim().isEmpty) return null;
    final text = (raw ?? '').trim();
    if (!RegExp(r'^[A-Za-z]{3}$').hasMatch(text)) return 'Three letters, e.g. EUR';
    return null;
  }

  String? _validateCountry(String? raw) {
    final text = (raw ?? '').trim();
    if (text.isEmpty) return null;
    if (!RegExp(r'^[A-Za-z]{2}$').hasMatch(text)) return 'Two letters, e.g. AT';
    return null;
  }

  String? _validateLanguage(String? raw) {
    final text = (raw ?? '').trim();
    if (text.isEmpty) return null;
    if (!RegExp(r'^[A-Za-z]{2}$').hasMatch(text)) return 'Two letters, e.g. de';
    return null;
  }

  Widget _field(
    TextEditingController ctrl,
    String label, {
    bool required = false,
    String? hint,
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
          border: const OutlineInputBorder(),
        ),
        validator: validator ??
            (required ? (v) => (v == null || v.isEmpty) ? '$label is required' : null : null),
      ),
    );
  }
}

/// The labelled, outlined box the organization dropdown sits in, so the picker
/// lines up with the text fields around it.
class _PickerShell extends StatelessWidget {
  const _PickerShell({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return InputDecorator(
      decoration: const InputDecoration(
        labelText: 'Organization',
        border: OutlineInputBorder(),
      ),
      child: child,
    );
  }
}
