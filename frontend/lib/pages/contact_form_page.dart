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
  late final TextEditingController _email;
  late final TextEditingController _phone;
  late final TextEditingController _address;
  late final TextEditingController _tags;
  late final TextEditingController _notes;

  /// The linked company, or null for someone unaffiliated. Not a text field
  /// any more: free text made "ACME" and "Acme" two different companies.
  String? _organizationId;

  bool get _isEdit => widget.contact != null;

  @override
  void initState() {
    super.initState();
    final c = widget.contact;
    _name = TextEditingController(text: c?.name);
    _email = TextEditingController(text: c?.email);
    _phone = TextEditingController(text: c?.phone);
    _address = TextEditingController(text: c?.address);
    _tags = TextEditingController(text: c?.tags.join(', '));
    _notes = TextEditingController(text: c?.notes);
    _organizationId = c?.organizationId ?? widget.initialOrganizationId;
  }

  @override
  void dispose() {
    for (final ctrl in [_name, _email, _phone, _address, _tags, _notes]) {
      ctrl.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    final tags = _tags.text.isEmpty
        ? <String>[]
        : _tags.text.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();

    final body = <String, dynamic>{
      'name': _name.text,
      // Always sent, including null: that is how a contact is unlinked from a
      // company, and PATCH only touches the fields it receives.
      'organization_id': _organizationId,
      if (_email.text.isNotEmpty) 'email': _email.text,
      if (_phone.text.isNotEmpty) 'phone': _phone.text,
      if (_address.text.isNotEmpty) 'address': _address.text,
      'tags': tags,
      if (_notes.text.isNotEmpty) 'notes': _notes.text,
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
            _organizationPicker(),
            _field(_email, 'Email'),
            _field(_phone, 'Phone'),
            _field(_address, 'Address'),
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

  Widget _field(
    TextEditingController ctrl,
    String label, {
    bool required = false,
    String? hint,
    int maxLines = 1,
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
        validator: required ? (v) => (v == null || v.isEmpty) ? '$label is required' : null : null,
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
