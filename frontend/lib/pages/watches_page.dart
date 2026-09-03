import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/date_time_text.dart';
import '../core/error_text.dart';
import '../core/web_download.dart';
import '../models/paged_result.dart';
import '../models/watch.dart';
import '../providers/deals_provider.dart';
import '../providers/tasks_provider.dart';
import '../providers/watches_provider.dart';
import '../widgets/confirm_dialog.dart';
import '../widgets/pagination_bar.dart';
import 'watch_form_page.dart';

/// What the list is showing. Defaults to [dueNow] — the sweep is the reason the
/// screen exists, and everything else is maintenance.
enum _Scope {
  dueNow('Due now', true, true),
  running('All active', null, true),
  everything('Everything', null, null);

  const _Scope(this.label, this.due, this.active);

  final String label;

  /// null means "no due filter"; true is the sweep list.
  final bool? due;

  /// null includes paused sources.
  final bool? active;
}

/// The watch list: job boards, careers pages and tender portals swept on a
/// cadence.
///
/// The intake end of the pipeline — everything else in the app records
/// opportunities that already exist; this is where they come from.
class WatchesPage extends ConsumerStatefulWidget {
  const WatchesPage({super.key});

  @override
  ConsumerState<WatchesPage> createState() => _WatchesPageState();
}

class _WatchesPageState extends ConsumerState<WatchesPage>
    with SingleTickerProviderStateMixin {
  final _searchController = TextEditingController();
  String _search = '';
  _Scope _scope = _Scope.dueNow;
  WatchKind? _kind;
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

  @override
  Widget build(BuildContext context) {
    final watchesAsync = ref.watch(
      watchesProvider((
        search: _search,
        kind: _kind,
        due: _scope.due,
        active: _scope.active,
        skip: _skip,
      )),
    );

    Widget detail() => watchesAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text(errorText(e))),
          data: (page) {
            final watch = _selectedId == null
                ? null
                : page.items.where((w) => w.id == _selectedId).firstOrNull;
            return _WatchDetail(watch: watch);
          },
        );

    Widget list({VoidCallback? onNarrow}) => _WatchList(
          search: _search,
          searchController: _searchController,
          scope: _scope,
          kind: _kind,
          selectedId: _selectedId,
          onSearchChanged: _onSearchChanged,
          onSearchCleared: () {
            _debounce?.cancel();
            _searchController.clear();
            setState(() {
              _search = '';
              _skip = 0;
            });
          },
          onScopeChanged: (scope) => setState(() {
            _scope = scope;
            _skip = 0;
          }),
          onKindChanged: (kind) => setState(() {
            _kind = kind;
            _skip = 0;
          }),
          onSelected: (id) {
            setState(() => _selectedId = id);
            onNarrow?.call();
          },
          watchesAsync: watchesAsync,
          onSkipChanged: (skip) => setState(() => _skip = skip),
        );

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 700) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(width: 400, child: list()),
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
                  list(onNarrow: () => _tabController.animateTo(1)),
                  detail(),
                ],
              ),
            ),
            TabBar(
              controller: _tabController,
              tabs: const [
                Tab(icon: Icon(Icons.travel_explore), text: 'Sources'),
                Tab(icon: Icon(Icons.info_outline), text: 'Detail'),
              ],
            ),
          ],
        );
      },
    );
  }
}

IconData _kindIcon(WatchKind kind) => switch (kind) {
      WatchKind.jobBoard => Icons.work_outline,
      WatchKind.careersPage => Icons.business_outlined,
      WatchKind.tenderPortal => Icons.gavel_outlined,
      WatchKind.other => Icons.link,
    };

class _WatchList extends StatelessWidget {
  const _WatchList({
    required this.search,
    required this.searchController,
    required this.scope,
    required this.kind,
    required this.selectedId,
    required this.onSearchChanged,
    required this.onSearchCleared,
    required this.onScopeChanged,
    required this.onKindChanged,
    required this.onSelected,
    required this.watchesAsync,
    required this.onSkipChanged,
  });

  final String search;
  final TextEditingController searchController;
  final _Scope scope;
  final WatchKind? kind;
  final String? selectedId;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onSearchCleared;
  final ValueChanged<_Scope> onScopeChanged;
  final ValueChanged<WatchKind?> onKindChanged;
  final ValueChanged<String> onSelected;
  final AsyncValue<PagedResult<Watch>> watchesAsync;
  final ValueChanged<int> onSkipChanged;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: searchController,
                  decoration: InputDecoration(
                    hintText: 'Search sources…',
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
                onPressed: () => Navigator.push<void>(
                  context,
                  MaterialPageRoute(builder: (_) => const WatchFormPage()),
                ),
                icon: const Icon(Icons.add),
                label: const Text('New'),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
          child: Row(
            children: [
              Expanded(
                child: DropdownButtonFormField<_Scope>(
                  initialValue: scope,
                  isDense: true,
                  decoration: const InputDecoration(isDense: true, border: OutlineInputBorder()),
                  items: [
                    for (final option in _Scope.values)
                      DropdownMenuItem(value: option, child: Text(option.label)),
                  ],
                  onChanged: (v) => onScopeChanged(v ?? scope),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: DropdownButtonFormField<WatchKind?>(
                  initialValue: kind,
                  isDense: true,
                  decoration: const InputDecoration(isDense: true, border: OutlineInputBorder()),
                  items: [
                    const DropdownMenuItem<WatchKind?>(value: null, child: Text('All kinds')),
                    for (final k in WatchKind.values)
                      DropdownMenuItem<WatchKind?>(value: k, child: Text(k.plural)),
                  ],
                  onChanged: onKindChanged,
                ),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: watchesAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: SelectableText(
                errorText(e),
                style: TextStyle(color: scheme.error),
              ),
            ),
            data: (page) {
              if (page.items.isEmpty) {
                return Center(
                  child: Text(
                    scope == _Scope.dueNow ? 'Nothing due. All swept.' : 'No sources yet.',
                  ),
                );
              }
              return Column(
                children: [
                  Expanded(
                    child: ListView.builder(
                      itemCount: page.items.length,
                      itemBuilder: (context, index) {
                        final watch = page.items[index];
                        return ListTile(
                          selected: watch.id == selectedId,
                          onTap: () => onSelected(watch.id),
                          leading: Icon(
                            _kindIcon(watch.kind),
                            color: watch.isDue ? scheme.primary : null,
                          ),
                          title: Text(
                            watch.name,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: watch.active ? null : Colors.grey,
                            ),
                          ),
                          subtitle: Text(
                            [
                              watch.dueLabel,
                              ?watch.organizationName,
                              watch.cadenceLabel,
                            ].join(' · '),
                            style: TextStyle(
                              color: watch.isDue ? scheme.primary : Colors.grey,
                            ),
                          ),
                          trailing: watch.active
                              ? null
                              : const Icon(Icons.pause_circle_outline, size: 18),
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

class _WatchDetail extends ConsumerWidget {
  const _WatchDetail({required this.watch});

  final Watch? watch;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (watch == null) {
      return const Center(child: Text('Select a source'));
    }
    final w = watch!;
    final scheme = Theme.of(context).colorScheme;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(_kindIcon(w.kind)),
              const SizedBox(width: 8),
              Expanded(
                child: Text(w.name, style: Theme.of(context).textTheme.titleLarge),
              ),
              IconButton(
                icon: const Icon(Icons.edit_outlined),
                tooltip: 'Edit',
                onPressed: () => Navigator.push<void>(
                  context,
                  MaterialPageRoute(builder: (_) => WatchFormPage(watch: w)),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Delete',
                onPressed: () => _confirmDelete(context, ref, w),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            '${w.kind.label} · ${w.cadenceLabel}',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.grey),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              FilledButton.icon(
                onPressed: () => _sweep(context, ref, w),
                icon: const Icon(Icons.open_in_new),
                label: const Text('Open & sweep'),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => _logCheck(context, ref, w),
                icon: const Icon(Icons.done),
                label: const Text('Log a check'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _Field(
            label: 'Status',
            value: w.active ? w.dueLabel : 'Paused — ${w.dueLabel}',
            color: w.isDue ? scheme.primary : null,
          ),
          _Field(label: 'URL', value: w.url),
          if (w.queryNote != null) _Field(label: 'What to look for', value: w.queryNote!),
          if (w.organizationName != null) _Field(label: 'Company', value: w.organizationName!),
          if (w.lastCheckedAt != null)
            _Field(label: 'Last swept', value: formatWhen(w.lastCheckedAt!)),
          // The question a single timestamp cannot answer: is this source
          // worth keeping?
          _Field(
            label: 'History',
            value: w.checkCount == 0
                ? 'Never swept'
                : '${w.foundCount} find${w.foundCount == 1 ? '' : 's'} '
                    'in ${w.checkCount} sweep${w.checkCount == 1 ? '' : 's'}',
          ),
          if (w.notes != null) _Field(label: 'Notes', value: w.notes!),
          const SizedBox(height: 8),
          _CheckHistory(watch: w),
        ],
      ),
    );
  }

  /// Open the source, then offer to log what it turned up — the two halves of
  /// the habit, in the order they actually happen.
  Future<void> _sweep(BuildContext context, WidgetRef ref, Watch w) async {
    openInNewTab(w.url);
    if (context.mounted) await _logCheck(context, ref, w);
  }

  Future<void> _logCheck(BuildContext context, WidgetRef ref, Watch w) async {
    final outcome = await showDialog<_CheckDraft>(
      context: context,
      builder: (_) => _CheckDialog(watch: w),
    );
    if (outcome == null || !context.mounted) return;

    try {
      await ref.read(watchesRepositoryProvider).check(
            w.id,
            outcome: outcome.outcome,
            note: outcome.note,
            createDeal: outcome.deal,
            createTask: outcome.task,
          );
    } catch (e) {
      if (context.mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not log the sweep.');
      }
      return;
    }
    ref.invalidate(watchesProvider);
    ref.invalidate(watchChecksProvider);
    ref.invalidate(dueWatchCountProvider);
    // A find may have created one of these.
    ref.invalidate(dealsProvider);
    ref.invalidate(allDealsProvider);
    ref.invalidate(tasksProvider);
    ref.invalidate(allTasksProvider);
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref, Watch w) async {
    final confirmed = await confirmDelete(
      context,
      title: 'Delete source?',
      message: '"${w.name}" and its ${w.checkCount} logged '
          'sweep${w.checkCount == 1 ? '' : 's'} will be permanently deleted. '
          'To stop checking it without losing the history, edit it and switch '
          'Active off instead.',
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(watchesRepositoryProvider).delete(w.id);
    } catch (e) {
      if (context.mounted) {
        showErrorSnackBar(context, e, prefix: 'Delete failed.');
      }
      return;
    }
    ref.invalidate(watchesProvider);
    ref.invalidate(dueWatchCountProvider);
  }
}

/// What the check dialog collected.
class _CheckDraft {
  const _CheckDraft({required this.outcome, this.note, this.deal, this.task});

  final CheckOutcome outcome;
  final String? note;
  final Map<String, dynamic>? deal;
  final Map<String, dynamic>? task;
}

/// Log one sweep, and capture what it found before the tab is closed.
class _CheckDialog extends StatefulWidget {
  const _CheckDialog({required this.watch});

  final Watch watch;

  @override
  State<_CheckDialog> createState() => _CheckDialogState();
}

class _CheckDialogState extends State<_CheckDialog> {
  final _note = TextEditingController();
  final _title = TextEditingController();
  bool _found = false;
  // What a find becomes. A tender portal almost always means a deal; a job
  // board more often means "go and talk to them".
  late bool _asDeal;

  @override
  void initState() {
    super.initState();
    _asDeal = widget.watch.kind == WatchKind.tenderPortal;
  }

  @override
  void dispose() {
    _note.dispose();
    _title.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('Sweep ${widget.watch.name}'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: false, label: Text('Nothing')),
                  ButtonSegment(value: true, label: Text('Found something')),
                ],
                selected: {_found},
                onSelectionChanged: (s) => setState(() => _found = s.first),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _note,
                maxLines: 2,
                decoration: InputDecoration(
                  labelText: 'Note (optional)',
                  hintText: _found ? 'IT-DL Rahmenvertrag, CPV 72000' : 'Site was down',
                  border: const OutlineInputBorder(),
                ),
              ),
              if (_found) ...[
                const SizedBox(height: 16),
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(value: true, label: Text('As a deal')),
                    ButtonSegment(value: false, label: Text('As a task')),
                  ],
                  selected: {_asDeal},
                  onSelectionChanged: (s) => setState(() => _asDeal = s.first),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _title,
                  decoration: InputDecoration(
                    labelText: _asDeal ? 'Deal title' : 'Task title',
                    hintText: _asDeal
                        ? 'IT-DL Rahmenvertrag'
                        : 'Approach them about the role',
                    helperText: 'Leave empty to just record the note.',
                    border: const OutlineInputBorder(),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            final note = _note.text.trim();
            final title = _title.text.trim();
            Navigator.pop(
              context,
              _CheckDraft(
                outcome: _found ? CheckOutcome.found : CheckOutcome.nothing,
                note: note.isEmpty ? null : note,
                deal: _found && _asDeal && title.isNotEmpty ? {'title': title} : null,
                task: _found && !_asDeal && title.isNotEmpty ? {'title': title} : null,
              ),
            );
          },
          child: const Text('Log it'),
        ),
      ],
    );
  }
}

/// Every sweep of this source, newest first. Append-only — there is no edit.
class _CheckHistory extends ConsumerStatefulWidget {
  const _CheckHistory({required this.watch});

  final Watch watch;

  @override
  ConsumerState<_CheckHistory> createState() => _CheckHistoryState();
}

class _CheckHistoryState extends ConsumerState<_CheckHistory> {
  int _skip = 0;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final async = ref.watch(
      watchChecksProvider((watchId: widget.watch.id, skip: _skip)),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Sweeps', style: Theme.of(context).textTheme.labelLarge),
        async.when(
          loading: () => const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: LinearProgressIndicator(),
          ),
          error: (e, _) => Text(errorText(e), style: TextStyle(color: scheme.error)),
          data: (page) => page.items.isEmpty
              ? const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    'Never swept yet.',
                    style: TextStyle(color: Colors.grey),
                  ),
                )
              : Column(
                  children: [
                    for (final check in page.items)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        leading: Icon(
                          check.found ? Icons.star : Icons.remove,
                          size: 18,
                          color: check.found ? scheme.primary : Colors.grey,
                        ),
                        title: Text(formatWhen(check.checkedAt)),
                        subtitle: Text(
                          check.note ?? check.outcome.label,
                          style: TextStyle(
                            color: check.found ? null : Colors.grey,
                          ),
                        ),
                        trailing: (check.createdDealId ?? check.createdTaskId) == null
                            ? null
                            : Tooltip(
                                message: check.createdDealId != null
                                    ? 'Became a deal'
                                    : 'Became a task',
                                child: Icon(
                                  check.createdDealId != null
                                      ? Icons.trending_up
                                      : Icons.task_alt,
                                  size: 18,
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
  const _Field({required this.label, required this.value, this.color});

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 2),
          SelectableText(
            value,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: color),
          ),
        ],
      ),
    );
  }
}
