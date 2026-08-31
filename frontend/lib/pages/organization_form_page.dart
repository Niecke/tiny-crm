import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/organization.dart';
import '../providers/contacts_provider.dart';
import '../providers/organizations_provider.dart';

/// Create or edit a company. Pops with the saved [Organization], so the caller
/// (the contact form's "new organization" button) can select it right away.
class OrganizationFormPage extends ConsumerStatefulWidget {
  const OrganizationFormPage({super.key, this.organization});

  final Organization? organization;

  @override
  ConsumerState<OrganizationFormPage> createState() => _OrganizationFormPageState();
}

class _OrganizationFormPageState extends ConsumerState<OrganizationFormPage> {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _name;
  late final TextEditingController _domain;
  late final TextEditingController _email;
  late final TextEditingController _phone;
  late final TextEditingController _address;
  late final TextEditingController _industry;
  late final TextEditingController _notes;

  bool get _isEdit => widget.organization != null;

  @override
  void initState() {
    super.initState();
    final o = widget.organization;
    _name = TextEditingController(text: o?.name);
    _domain = TextEditingController(text: o?.domain);
    _email = TextEditingController(text: o?.email);
    _phone = TextEditingController(text: o?.phone);
    _address = TextEditingController(text: o?.address);
    _industry = TextEditingController(text: o?.industry);
    _notes = TextEditingController(text: o?.notes);
  }

  @override
  void dispose() {
    for (final ctrl in [_name, _domain, _email, _phone, _address, _industry, _notes]) {
      ctrl.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);

    // Empty means "clear this field", not "leave it alone": on an edit the
    // server would otherwise keep a value the user just deleted.
    String? orNull(TextEditingController ctrl) =>
        ctrl.text.trim().isEmpty ? null : ctrl.text.trim();

    final body = <String, dynamic>{
      'name': _name.text.trim(),
      'domain': orNull(_domain),
      'email': orNull(_email),
      'phone': orNull(_phone),
      'address': orNull(_address),
      'industry': orNull(_industry),
      'notes': orNull(_notes),
    };

    final repo = ref.read(organizationsRepositoryProvider);
    final Organization saved;
    try {
      if (_isEdit) {
        saved = await repo.update(widget.organization!.id, body);
      } else {
        saved = await repo.create(body);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not save organization.');
        setState(() => _saving = false);
      }
      return;
    }

    ref.invalidate(organizationsProvider);
    ref.invalidate(allOrganizationsProvider);
    // A renamed company shows up on every contact that points at it.
    ref.invalidate(contactsProvider);
    ref.invalidate(allContactsProvider);

    if (mounted) Navigator.pop(context, saved);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEdit ? 'Edit Organization' : 'New Organization'),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            _field(_name, 'Name', required: true),
            _field(_domain, 'Domain', hint: 'acme.example'),
            // Company-level, not personal: the address letters and invoices go
            // to, the shared mailbox, the switchboard.
            _field(_email, 'Email', hint: 'office@acme.example'),
            _field(_phone, 'Phone', hint: '+49 30 123456'),
            _field(_address, 'Address', maxLines: 2),
            _field(_industry, 'Industry'),
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
