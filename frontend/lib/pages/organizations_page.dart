import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/organization.dart';
import '../models/paged_result.dart';
import '../providers/contacts_provider.dart';
import '../providers/organizations_provider.dart';
import '../widgets/attached_documents_section.dart';
import '../widgets/attached_interactions_section.dart';
import '../widgets/confirm_dialog.dart';
import '../widgets/pagination_bar.dart';
import 'contact_detail_page.dart';
import 'contact_form_page.dart';
import 'organization_form_page.dart';

/// The companies list: who we do business with, and who we know there.
///
/// Same shape as the projects screen — list beside detail on a wide window,
/// two tabs under 700px.
class OrganizationsPage extends ConsumerStatefulWidget {
  const OrganizationsPage({super.key});

  @override
  ConsumerState<OrganizationsPage> createState() => _OrganizationsPageState();
}

class _OrganizationsPageState extends ConsumerState<OrganizationsPage>
    with SingleTickerProviderStateMixin {
  final _searchController = TextEditingController();
  String _search = '';
  int _skip = 0;
  String? _selectedId;
  Timer? _debounce;
  late final TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    _tabController.dispose();
    super.dispose();
  }

  void _onSearchChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(seconds: 1), () {
      // Back to page 1: the old offset means nothing here.
      setState(() {
        _search = value.trim();
        _skip = 0;
      });
    });
  }

  void _onSearchCleared() {
    _debounce?.cancel();
    _searchController.clear();
    setState(() {
      _search = '';
      _skip = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    final organizationsAsync = ref.watch(
      organizationsProvider((search: _search, skip: _skip)),
    );

    Widget detail() {
      return organizationsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(errorText(e))),
        data: (page) {
          final organization = _selectedId == null
              ? null
              : page.items.where((o) => o.id == _selectedId).firstOrNull;
          return _OrganizationDetail(organization: organization);
        },
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 700) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 360,
                child: _OrganizationList(
                  search: _search,
                  searchController: _searchController,
                  selectedId: _selectedId,
                  onSearchChanged: _onSearchChanged,
                  onSearchCleared: _onSearchCleared,
                  onSelected: (id) => setState(() => _selectedId = id),
                  onNarrow: null,
                  organizationsAsync: organizationsAsync,
                  onSkipChanged: (skip) => setState(() => _skip = skip),
                ),
              ),
              const VerticalDivider(width: 1),
              Expanded(child: detail()),
            ],
          );
        }

        return Column(
          children: [
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  _OrganizationList(
                    search: _search,
                    searchController: _searchController,
                    selectedId: _selectedId,
                    onSearchChanged: _onSearchChanged,
                    onSearchCleared: _onSearchCleared,
                    onSelected: (id) {
                      setState(() => _selectedId = id);
                      _tabController.animateTo(1);
                    },
                    onNarrow: () => _tabController.animateTo(1),
                    organizationsAsync: organizationsAsync,
                    onSkipChanged: (skip) => setState(() => _skip = skip),
                  ),
                  detail(),
                ],
              ),
            ),
            TabBar(
              controller: _tabController,
              tabs: const [
                Tab(icon: Icon(Icons.business_outlined), text: 'Organizations'),
                Tab(icon: Icon(Icons.info_outline), text: 'Detail'),
              ],
            ),
          ],
        );
      },
    );
  }
}

class _OrganizationList extends StatelessWidget {
  const _OrganizationList({
    required this.search,
    required this.searchController,
    required this.selectedId,
    required this.onSearchChanged,
    required this.onSearchCleared,
    required this.onSelected,
    required this.onNarrow,
    required this.organizationsAsync,
    required this.onSkipChanged,
  });

  final String search;
  final TextEditingController searchController;
  final String? selectedId;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onSearchCleared;
  final ValueChanged<String> onSelected;
  final VoidCallback? onNarrow;
  final AsyncValue<PagedResult<Organization>> organizationsAsync;
  final ValueChanged<int> onSkipChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: searchController,
                  decoration: InputDecoration(
                    hintText: 'Search name or domain…',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: search.isEmpty
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.clear),
                            onPressed: onSearchCleared,
                          ),
                    isDense: true,
                    border: const OutlineInputBorder(),
                  ),
                  onChanged: onSearchChanged,
                ),
              ),
              const SizedBox(width: 8),
              FilledButton.icon(
                onPressed: () => Navigator.push<Organization>(
                  context,
                  MaterialPageRoute(builder: (_) => const OrganizationFormPage()),
                ),
                icon: const Icon(Icons.add),
                label: const Text('New'),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: organizationsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: SelectableText(
                errorText(e),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
            data: (page) {
              if (page.items.isEmpty) {
                return const Center(child: Text('No organizations yet.'));
              }
              return Column(
                children: [
                  Expanded(
                    child: ListView.builder(
                      itemCount: page.items.length,
                      itemBuilder: (context, index) {
                        final organization = page.items[index];
                        return ListTile(
                          selected: organization.id == selectedId,
                          onTap: () {
                            onSelected(organization.id);
                            onNarrow?.call();
                          },
                          title: Text(
                            organization.name,
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          subtitle: Text(
                            [
                              if (organization.domain != null) organization.domain!,
                              organization.contactCount == 1
                                  ? '1 contact'
                                  : '${organization.contactCount} contacts',
                            ].join(' · '),
                          ),
                        );
                      },
                    ),
                  ),
                  PaginationBar(page: page, onSkipChanged: onSkipChanged),
                ],
              );
            },
          ),
        ),
      ],
    );
  }
}

class _OrganizationDetail extends ConsumerWidget {
  const _OrganizationDetail({required this.organization});

  final Organization? organization;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (organization == null) {
      return const Center(child: Text('Select an organization'));
    }
    final o = organization!;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(o.name, style: Theme.of(context).textTheme.titleLarge),
              ),
              IconButton(
                icon: const Icon(Icons.edit_outlined),
                tooltip: 'Edit',
                onPressed: () => Navigator.push<Organization>(
                  context,
                  MaterialPageRoute(
                    builder: (_) => OrganizationFormPage(organization: o),
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Delete',
                onPressed: () => _confirmDelete(context, ref, o),
              ),
            ],
          ),
          if (o.industry != null)
            Text(
              o.industry!,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: Colors.grey),
            ),
          const SizedBox(height: 16),
          if (o.domain != null) _Field(label: 'Domain', value: o.domain!),
          if (o.email != null) _Field(label: 'Email', value: o.email!),
          if (o.phone != null) _Field(label: 'Phone', value: o.phone!),
          if (o.address != null) _Field(label: 'Address', value: o.address!),
          if (o.notes != null) _Field(label: 'Notes', value: o.notes!),
          const SizedBox(height: 8),
          _OrganizationContacts(organization: o),
          const SizedBox(height: 8),
          // The switchboard call, the company NDA — things about the company
          // rather than about any one person there.
          AttachedInteractionsSection(organizationId: o.id),
          AttachedDocumentsSection(organizationId: o.id),
        ],
      ),
    );
  }

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    Organization o,
  ) async {
    final confirmed = await confirmDelete(
      context,
      title: 'Delete organization?',
      message: '"${o.name}" will be permanently deleted. '
          'Its contacts are kept, without a company.',
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(organizationsRepositoryProvider).delete(o.id);
    } catch (e) {
      if (context.mounted) {
        showErrorSnackBar(context, e, prefix: 'Delete failed.');
      }
      return;
    }
    ref.invalidate(organizationsProvider);
    ref.invalidate(allOrganizationsProvider);
    // Every contact that pointed here just lost its company.
    ref.invalidate(contactsProvider);
    ref.invalidate(allContactsProvider);
  }
}

/// Everyone we know at this company — the question free-text company could
/// never answer.
class _OrganizationContacts extends ConsumerStatefulWidget {
  const _OrganizationContacts({required this.organization});

  final Organization organization;

  @override
  ConsumerState<_OrganizationContacts> createState() => _OrganizationContactsState();
}

class _OrganizationContactsState extends ConsumerState<_OrganizationContacts> {
  int _skip = 0;

  @override
  Widget build(BuildContext context) {
    final organization = widget.organization;
    final contactsAsync = ref.watch(
      contactsProvider((
        search: '',
        organizationId: organization.id,
        skip: _skip,
      )),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Contacts', style: Theme.of(context).textTheme.titleSmall),
            const Spacer(),
            TextButton.icon(
              icon: const Icon(Icons.person_add_alt, size: 18),
              label: const Text('Add'),
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => ContactFormPage(
                    initialOrganizationId: organization.id,
                  ),
                ),
              ),
            ),
          ],
        ),
        contactsAsync.when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: LinearProgressIndicator(),
          ),
          error: (e, _) => Text(
            errorText(e),
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
          data: (page) => page.items.isEmpty
              ? const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    'Nobody here yet.',
                    style: TextStyle(color: Colors.grey),
                  ),
                )
              : Column(
                  children: [
                    for (final contact in page.items)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.person_outline),
                        title: Text(contact.name),
                        subtitle: contact.email == null ? null : Text(contact.email!),
                        onTap: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => ContactDetailPage(contact: contact),
                          ),
                        ),
                      ),
                    PaginationBar(
                      page: page,
                      onSkipChanged: (skip) => setState(() => _skip = skip),
                    ),
                  ],
                ),
        ),
      ],
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 2),
          SelectableText(value, style: Theme.of(context).textTheme.bodyLarge),
        ],
      ),
    );
  }
}
