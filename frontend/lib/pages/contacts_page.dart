import 'package:flutter/material.dart';

import '../api.dart';
import '../models/contact.dart';
import 'contact_detail_page.dart';
import 'contact_form_page.dart';

class ContactsPage extends StatefulWidget {
  const ContactsPage({super.key});

  @override
  State<ContactsPage> createState() => _ContactsPageState();
}

class _ContactsPageState extends State<ContactsPage> {
  late Future<List<Contact>> _contactsFuture;

  @override
  void initState() {
    super.initState();
    _contactsFuture = _fetchContacts();
  }

  Future<List<Contact>> _fetchContacts() async {
    final res = await dio.get<List<dynamic>>('/contacts/');
    return res.data!.map((e) => Contact.fromJson(e as Map<String, dynamic>)).toList();
  }

  void _refresh() => setState(() { _contactsFuture = _fetchContacts(); });

  // Navigator.push returns a Future that resolves when the pushed page pops.
  // Passing true back signals that something changed → refresh the list.
  Future<void> _openCreate() async {
    final created = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => const ContactFormPage()),
    );
    if (created == true && mounted) _refresh();
  }

  Future<void> _openDetail(Contact contact) async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => ContactDetailPage(contact: contact)),
    );
    if (changed == true && mounted) _refresh();
  }

  Future<void> _openEdit(Contact contact) async {
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => ContactFormPage(contact: contact)),
    );
    if (saved == true && mounted) _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Contacts card — fixed width, scrolls independently
          SizedBox(
            width: 360,
            child: Card(
              child: Column(
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('Contacts', style: Theme.of(context).textTheme.titleMedium),
                        IconButton(
                          onPressed: _openCreate,
                          icon: const Icon(Icons.add),
                          tooltip: 'New Contact',
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1),
                  Expanded(
                    child: FutureBuilder<List<Contact>>(
                      future: _contactsFuture,
                      builder: (context, snapshot) => _buildBody(snapshot),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 16),
          // Right panel — future content goes here
          const Expanded(child: SizedBox()),
        ],
      ),
    );
  }

  Widget _buildBody(AsyncSnapshot<List<Contact>> snapshot) {
    if (snapshot.connectionState == ConnectionState.waiting) {
      return const Center(child: CircularProgressIndicator());
    }
    if (snapshot.hasError) {
      return Center(
        child: SelectableText(
          'Error: ${snapshot.error}',
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
      );
    }
    final contacts = snapshot.data!;
    if (contacts.isEmpty) {
      return const Center(child: Text('No contacts yet. Create one!'));
    }
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      itemCount: contacts.length,
      itemBuilder: (context, index) => _ContactCard(
        contact: contacts[index],
        onTap: () => _openDetail(contacts[index]),
        onEdit: () => _openEdit(contacts[index]),
      ),
    );
  }
}

class _ContactCard extends StatelessWidget {
  const _ContactCard({
    required this.contact,
    required this.onTap,
    required this.onEdit,
  });

  final Contact contact;
  final VoidCallback onTap;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 4),
      child: ListTile(
        onTap: onTap,
        title: Text(contact.name),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (contact.company != null) Text(contact.company!),
            if (contact.email != null)
              Text(contact.email!, style: const TextStyle(color: Colors.grey)),
            if (contact.tags.isNotEmpty)
              Wrap(
                spacing: 4,
                children: contact.tags
                    .map((t) => Chip(label: Text(t), visualDensity: VisualDensity.compact))
                    .toList(),
              ),
          ],
        ),
        isThreeLine: true,
        trailing: IconButton(
          icon: const Icon(Icons.edit_outlined),
          tooltip: 'Edit',
          onPressed: onEdit,
        ),
      ),
    );
  }
}
