import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web/web.dart' as web;

import '../models/contact.dart';
import '../models/document.dart';
import '../models/project.dart';
import '../models/task.dart';
import '../providers/contacts_provider.dart';
import '../providers/documents_provider.dart';
import '../providers/projects_provider.dart';
import '../providers/tasks_provider.dart';
import 'contact_detail_page.dart';
import 'project_form_page.dart';
import 'task_form_page.dart';

class ProjectsPage extends ConsumerStatefulWidget {
  const ProjectsPage({super.key});

  @override
  ConsumerState<ProjectsPage> createState() => _ProjectsPageState();
}

class _ProjectsPageState extends ConsumerState<ProjectsPage>
    with SingleTickerProviderStateMixin {
  final _searchController = TextEditingController();
  String _search = '';
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

  @override
  Widget build(BuildContext context) {
    final projectsAsync = ref.watch(projectsProvider(_search));

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 700) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 360,
                child: _ProjectList(
                  search: _search,
                  searchController: _searchController,
                  selectedId: _selectedId,
                  onSearchChanged: (v) {
                    _debounce?.cancel();
                    _debounce = Timer(const Duration(seconds: 1), () {
                      setState(() => _search = v.trim());
                    });
                  },
                  onSearchCleared: () {
                    _debounce?.cancel();
                    _searchController.clear();
                    setState(() => _search = '');
                  },
                  onSelected: (id) => setState(() => _selectedId = id),
                  onNarrow: null,
                  projectsAsync: projectsAsync,
                ),
              ),
              const VerticalDivider(width: 1),
              Expanded(
                child: projectsAsync.when(
                  loading: () => const Center(child: CircularProgressIndicator()),
                  error: (e, _) => Center(child: Text('Error: $e')),
                  data: (projects) {
                    final project = _selectedId == null
                        ? null
                        : projects.where((p) => p.id == _selectedId).firstOrNull;
                    return _ProjectDetail(
                      project: project,
                      onChanged: () => ref.invalidate(projectsProvider),
                    );
                  },
                ),
              ),
            ],
          );
        }

        return DefaultTabController(
          length: 2,
          child: Column(
            children: [
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _ProjectList(
                      search: _search,
                      searchController: _searchController,
                      selectedId: _selectedId,
                      onSearchChanged: (v) {
                        _debounce?.cancel();
                        _debounce = Timer(const Duration(seconds: 1), () {
                          setState(() => _search = v.trim());
                        });
                      },
                      onSearchCleared: () {
                        _debounce?.cancel();
                        _searchController.clear();
                        setState(() => _search = '');
                      },
                      onSelected: (id) {
                        setState(() => _selectedId = id);
                        _tabController.animateTo(1);
                      },
                      onNarrow: () => _tabController.animateTo(1),
                      projectsAsync: projectsAsync,
                    ),
                    projectsAsync.when(
                      loading: () =>
                          const Center(child: CircularProgressIndicator()),
                      error: (e, _) => Center(child: Text('Error: $e')),
                      data: (projects) {
                        final project = _selectedId == null
                            ? null
                            : projects
                                .where((p) => p.id == _selectedId)
                                .firstOrNull;
                        return _ProjectDetail(
                          project: project,
                          onChanged: () => ref.invalidate(projectsProvider),
                        );
                      },
                    ),
                  ],
                ),
              ),
              TabBar(
                controller: _tabController,
                tabs: const [
                  Tab(icon: Icon(Icons.folder_outlined), text: 'Projects'),
                  Tab(icon: Icon(Icons.info_outline), text: 'Detail'),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _ProjectList extends StatelessWidget {
  const _ProjectList({
    required this.search,
    required this.searchController,
    required this.selectedId,
    required this.onSearchChanged,
    required this.onSearchCleared,
    required this.onSelected,
    required this.onNarrow,
    required this.projectsAsync,
  });

  final String search;
  final TextEditingController searchController;
  final String? selectedId;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onSearchCleared;
  final ValueChanged<String> onSelected;
  final VoidCallback? onNarrow;
  final AsyncValue<List<Project>> projectsAsync;

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
                    hintText: 'Search projects…',
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
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => const ProjectFormPage(),
                  ),
                ),
                icon: const Icon(Icons.add),
                label: const Text('New'),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: projectsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: SelectableText(
                'Error: $e',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
            ),
            data: (projects) {
              if (projects.isEmpty) {
                return const Center(child: Text('No projects yet.'));
              }
              final grouped = <ProjectStatus, List<Project>>{
                ProjectStatus.active: [],
                ProjectStatus.upcoming: [],
                ProjectStatus.completed: [],
              };
              for (final p in projects) {
                grouped[statusOf(p)]!.add(p);
              }
              final items = <Widget>[];
              for (final status in ProjectStatus.values) {
                final list = grouped[status]!;
                if (list.isEmpty) continue;
                items.add(
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
                    child: Text(
                      switch (status) {
                        ProjectStatus.active => 'Active',
                        ProjectStatus.upcoming => 'Upcoming',
                        ProjectStatus.completed => 'Completed',
                      },
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            color: Theme.of(context).colorScheme.primary,
                          ),
                    ),
                  ),
                );
                for (final p in list) {
                  items.add(
                    ListTile(
                      selected: p.id == selectedId,
                      onTap: () {
                        onSelected(p.id);
                        onNarrow?.call();
                      },
                      title: Text(
                        p.name,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      subtitle: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(_formatRange(p.startDate, p.endDate)),
                          Text(
                            '${p.contactIds.length} contacts · ${p.taskIds.length} tasks · ${p.documentIds.length} docs',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                      isThreeLine: true,
                    ),
                  );
                }
              }
              return ListView(children: items);
            },
          ),
        ),
      ],
    );
  }

  String _formatRange(DateTime start, DateTime? end) {
    String fmt(DateTime d) =>
        '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    return end == null ? 'From ${fmt(start)}' : '${fmt(start)} – ${fmt(end)}';
  }
}

class _ProjectDetail extends ConsumerWidget {
  const _ProjectDetail({required this.project, required this.onChanged});

  final Project? project;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (project == null) {
      return const Center(child: Text('Select a project'));
    }
    final p = project!;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(p.name, style: Theme.of(context).textTheme.titleLarge),
              ),
              IconButton(
                icon: const Icon(Icons.edit_outlined),
                tooltip: 'Edit',
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => ProjectFormPage(project: p),
                  ),
                ).then((_) => onChanged()),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Delete',
                onPressed: () => _confirmDelete(context, ref, p),
              ),
            ],
          ),
          Text(
            _formatRange(p.startDate, p.endDate),
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Colors.grey,
                ),
          ),
          if (p.description != null && p.description!.isNotEmpty) ...[
            const SizedBox(height: 16),
            MarkdownBody(data: p.description!),
          ],
          const SizedBox(height: 24),
          _LinkSection<Contact>(
            title: 'Contacts',
            linkedIds: p.contactIds,
            allAsync: ref.watch(contactsProvider('')),
            labelOf: (c) => c.name,
            idOf: (c) => c.id,
            onUpdate: (ids) => _updateLinks(ref, p, contactIds: ids),
            onTap: (ctx, c) => Navigator.push(
              ctx,
              MaterialPageRoute(builder: (_) => ContactDetailPage(contact: c)),
            ),
          ),
          const SizedBox(height: 16),
          _LinkSection<Task>(
            title: 'Tasks',
            linkedIds: p.taskIds,
            allAsync: ref.watch(
              tasksProvider((search: '', includeDone: true)),
            ),
            labelOf: (t) => t.title,
            idOf: (t) => t.id,
            onUpdate: (ids) => _updateLinks(ref, p, taskIds: ids),
            onTap: (ctx, t) => Navigator.push(
              ctx,
              MaterialPageRoute(builder: (_) => TaskFormPage(task: t)),
            ),
          ),
          const SizedBox(height: 16),
          _LinkSection<Document>(
            title: 'Documents',
            linkedIds: p.documentIds,
            allAsync: ref.watch(documentsProvider('')),
            labelOf: (d) => d.title,
            idOf: (d) => d.id,
            onUpdate: (ids) => _updateLinks(ref, p, documentIds: ids),
            onTap: (ctx, d) => _showDocumentInfo(ctx, d),
          ),
        ],
      ),
    );
  }

  Future<void> _updateLinks(
    WidgetRef ref,
    Project p, {
    List<String>? contactIds,
    List<String>? taskIds,
    List<String>? documentIds,
  }) async {
    final body = <String, dynamic>{};
    if (contactIds != null) body['contact_ids'] = contactIds;
    if (taskIds != null) body['task_ids'] = taskIds;
    if (documentIds != null) body['document_ids'] = documentIds;
    await ref.read(projectsRepositoryProvider).update(p.id, body);
    ref.invalidate(projectsProvider);
  }

  Future<void> _confirmDelete(
    BuildContext context,
    WidgetRef ref,
    Project p,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete project?'),
        content: Text('"${p.name}" will be permanently deleted.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(ctx).colorScheme.error,
            ),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(projectsRepositoryProvider).delete(p.id);
    ref.invalidate(projectsProvider);
  }

  void _showDocumentInfo(BuildContext context, Document d) {
    showDialog<void>(
      context: context,
      builder: (_) => _DocumentInfoDialog(doc: d),
    );
  }

  String _formatRange(DateTime start, DateTime? end) {
    String fmt(DateTime d) =>
        '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    return end == null ? 'From ${fmt(start)}' : '${fmt(start)} – ${fmt(end)}';
  }
}

class _LinkSection<T> extends StatelessWidget {
  const _LinkSection({
    required this.title,
    required this.linkedIds,
    required this.allAsync,
    required this.labelOf,
    required this.idOf,
    required this.onUpdate,
    this.onTap,
  });

  final String title;
  final List<String> linkedIds;
  final AsyncValue<List<T>> allAsync;
  final String Function(T) labelOf;
  final String Function(T) idOf;
  final Future<void> Function(List<String>) onUpdate;
  final void Function(BuildContext, T)? onTap;

  @override
  Widget build(BuildContext context) {
    return allAsync.when(
      loading: () => const SizedBox.shrink(),
      error: (e, _) => Text('Error loading $title: $e'),
      data: (all) {
        final linkedSet = linkedIds.toSet();
        final linked = all.where((item) => linkedSet.contains(idOf(item))).toList();
        final unlinked = all.where((item) => !linkedSet.contains(idOf(item))).toList();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                const Spacer(),
                if (unlinked.isNotEmpty)
                  TextButton.icon(
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add'),
                    onPressed: () =>
                        _showAddDialog(context, unlinked, linked),
                  ),
              ],
            ),
            if (linked.isEmpty)
              Text(
                'None linked.',
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: Colors.grey),
              )
            else
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: linked
                    .map(
                      (item) => InputChip(
                        label: Text(labelOf(item)),
                        onPressed: onTap != null
                            ? () => onTap!(context, item)
                            : null,
                        onDeleted: () {
                          final newIds = List<String>.from(linkedIds)
                            ..remove(idOf(item));
                          onUpdate(newIds);
                        },
                        deleteIcon: const Icon(Icons.close, size: 16),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    )
                    .toList(),
              ),
          ],
        );
      },
    );
  }

  Future<void> _showAddDialog(
    BuildContext context,
    List<T> unlinked,
    List<T> linked,
  ) async {
    final selected = await showDialog<T>(
      context: context,
      builder: (ctx) => SimpleDialog(
        title: Text('Add $title'),
        children: unlinked
            .map(
              (item) => SimpleDialogOption(
                onPressed: () => Navigator.pop(ctx, item),
                child: Text(labelOf(item)),
              ),
            )
            .toList(),
      ),
    );
    if (selected == null) return;
    final newIds = [...linkedIds, idOf(selected)];
    await onUpdate(newIds);
  }
}

class _DocumentInfoDialog extends ConsumerStatefulWidget {
  const _DocumentInfoDialog({required this.doc});

  final Document doc;

  @override
  ConsumerState<_DocumentInfoDialog> createState() =>
      _DocumentInfoDialogState();
}

class _DocumentInfoDialogState extends ConsumerState<_DocumentInfoDialog> {
  bool _downloading = false;

  Future<void> _download() async {
    setState(() => _downloading = true);
    try {
      final bytes =
          await ref.read(documentsRepositoryProvider).downloadBytes(widget.doc.id);
      final ext =
          {'pdf': 'pdf', 'markdown': 'md', 'txt': 'txt'}[widget.doc.format] ??
          'bin';
      _triggerBrowserDownload(
        bytes,
        '${widget.doc.title}.$ext',
        _mimeType(widget.doc.format),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Download failed: $e')));
      }
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  void _triggerBrowserDownload(List<int> bytes, String filename, String mimeType) {
    final jsBytes = bytes.map((b) => b.toJS).toList().toJS;
    final blob = web.Blob(jsBytes, web.BlobPropertyBag(type: mimeType));
    final url = web.URL.createObjectURL(blob);
    final anchor = web.document.createElement('a') as web.HTMLAnchorElement;
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    web.URL.revokeObjectURL(url);
  }

  String _mimeType(String fmt) => switch (fmt) {
        'pdf' => 'application/pdf',
        'markdown' => 'text/markdown',
        _ => 'text/plain',
      };

  String _humanSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  @override
  Widget build(BuildContext context) {
    final doc = widget.doc;
    return AlertDialog(
      title: Text(doc.title),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (doc.hasPreview)
                FutureBuilder<Uint8List>(
                  future: ref
                      .read(documentsRepositoryProvider)
                      .downloadPreviewBytes(doc.id),
                  builder: (context, snapshot) {
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const SizedBox(
                        height: 200,
                        child: Center(child: CircularProgressIndicator()),
                      );
                    }
                    if (snapshot.hasError || snapshot.data == null) {
                      return const SizedBox.shrink();
                    }
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: Image.memory(
                          snapshot.data!,
                          width: double.infinity,
                          fit: BoxFit.contain,
                        ),
                      ),
                    );
                  },
                ),
              Text(
                '${doc.format.toUpperCase()} · ${_humanSize(doc.size)}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (doc.description != null && doc.description!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(doc.description!),
              ],
              if (doc.tags.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 4,
                  runSpacing: 4,
                  children: doc.tags
                      .map(
                        (t) => Chip(
                          label: Text(t),
                          visualDensity: VisualDensity.compact,
                          materialTapTargetSize:
                              MaterialTapTargetSize.shrinkWrap,
                        ),
                      )
                      .toList(),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Close'),
        ),
        FilledButton.icon(
          onPressed: _downloading ? null : _download,
          icon: _downloading
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.download),
          label: const Text('Download'),
        ),
      ],
    );
  }
}
