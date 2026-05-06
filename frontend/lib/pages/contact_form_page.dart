import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/contact.dart';
import '../providers/contacts_provider.dart';

// ConsumerStatefulWidget = StatefulWidget with ref.
// Use when you need both local mutable state (form controllers) and providers.
class ContactFormPage extends ConsumerStatefulWidget {
  const ContactFormPage({super.key, this.contact});

  final Contact? contact;

  @override
  ConsumerState<ContactFormPage> createState() => _ContactFormPageState();
}

class _ContactFormPageState extends ConsumerState<ContactFormPage> {
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  late final TextEditingController _name;
  late final TextEditingController _company;
  late final TextEditingController _email;
  late final TextEditingController _phone;
  late final TextEditingController _address;
  late final TextEditingController _tags;
  late final TextEditingController _notes;

  bool get _isEdit => widget.contact != null;

  @override
  void initState() {
    super.initState();
    final c = widget.contact;
    _name = TextEditingController(text: c?.name);
    _company = TextEditingController(text: c?.company);
    _email = TextEditingController(text: c?.email);
    _phone = TextEditingController(text: c?.phone);
    _address = TextEditingController(text: c?.address);
    _tags = TextEditingController(text: c?.tags.join(', '));
    _notes = TextEditingController(text: c?.notes);
  }

  @override
  void dispose() {
    for (final ctrl in [_name, _company, _email, _phone, _address, _tags, _notes]) {
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

    final body = {
      'name': _name.text,
      if (_company.text.isNotEmpty) 'company': _company.text,
      if (_email.text.isNotEmpty) 'email': _email.text,
      if (_phone.text.isNotEmpty) 'phone': _phone.text,
      if (_address.text.isNotEmpty) 'address': _address.text,
      'tags': tags,
      if (_notes.text.isNotEmpty) 'notes': _notes.text,
    };

    final repo = ref.read(contactsRepositoryProvider);
    if (_isEdit) {
      await repo.update(widget.contact!.id, body);
    } else {
      await repo.create(body);
    }

    // Invalidate here — every watcher of contactsProvider refetches automatically
    ref.invalidate(contactsProvider);

    if (mounted) Navigator.pop(context);
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
            _field(_company, 'Company'),
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
