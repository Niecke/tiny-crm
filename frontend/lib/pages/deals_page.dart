import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/date_time_text.dart';
import '../core/error_text.dart';
import '../models/deal.dart';
import '../models/paged_result.dart';
import '../providers/deals_provider.dart';
import '../widgets/confirm_dialog.dart';
import '../widgets/linked_tasks_section.dart';
import '../widgets/pagination_bar.dart';
import 'deal_form_page.dart';

/// What the list is showing. One control rather than two, because the 380px
/// column has no room for a stage filter *and* a status switch.
///
/// Defaults to [onMyPlate] — everything not finished, which deliberately
/// includes won and running work. Filtering to "still competing" would drop a
/// long engagement off the board the day it was won, which is exactly what the
/// `running` stage exists to prevent.
enum _Scope {
  onMyPlate('On my plate', null, DealStatus.active),
  competing('Still competing', null, DealStatus.open),
  wonEver('Won (any state)', null, DealStatus.won),
  finished('Finished', null, DealStatus.finished),
  all('All deals', null, null),
  lead('· Lead', DealStage.lead, null),
  qualified('· Qualified', DealStage.qualified, null),
  proposal('· Proposal', DealStage.proposal, null),
  negotiation('· Negotiation', DealStage.negotiation, null),
  won('· Won', DealStage.won, null),
  running('· Running', DealStage.running, null),
  completed('· Completed', DealStage.completed, null),
  lost('· Lost', DealStage.lost, null);

  const _Scope(this.label, this.stage, this.status);

  final String label;
  final DealStage? stage;
  final DealStatus? status;
}

/// The pipeline: what is in play, what it is worth, and what came of it.
///
/// Same shape as the organizations screen — list beside detail on a wide
/// window, two tabs under 700px.
class DealsPage extends ConsumerStatefulWidget {
  const DealsPage({super.key});

  @override
  ConsumerState<DealsPage> createState() => _DealsPageState();
}

class _DealsPageState extends ConsumerState<DealsPage> with SingleTickerProviderStateMixin {
  final _searchController = TextEditingController();
  String _search = '';
  _Scope _scope = _Scope.onMyPlate;
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
    final dealsAsync = ref.watch(
      dealsProvider((
        search: _search,
        stage: _scope.stage,
        status: _scope.status,
        skip: _skip,
      )),
    );

    Widget detail() {
      return dealsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(errorText(e))),
        data: (page) {
          final deal =
              _selectedId == null ? null : page.items.where((d) => d.id == _selectedId).firstOrNull;
          return _DealDetail(deal: deal);
        },
      );
    }

    Widget list({VoidCallback? onNarrow}) => _DealList(
          search: _search,
          searchController: _searchController,
          scope: _scope,
          selectedId: _selectedId,
          onSearchChanged: _onSearchChanged,
          onSearchCleared: _onSearchCleared,
          onScopeChanged: (scope) => setState(() {
            _scope = scope;
            _skip = 0;
          }),
          onSelected: (id) {
            setState(() => _selectedId = id);
            onNarrow?.call();
          },
          dealsAsync: dealsAsync,
          onSkipChanged: (skip) => setState(() => _skip = skip),
        );

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 700) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(width: 380, child: list()),
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
                Tab(icon: Icon(Icons.trending_up), text: 'Deals'),
                Tab(icon: Icon(Icons.info_outline), text: 'Detail'),
              ],
            ),
          ],
        );
      },
    );
  }
}

/// Colour per stage: closed deals read at a glance, and won must never look
/// like lost.
Color _stageColor(DealStage stage, ColorScheme scheme) => switch (stage) {
      // Won and still being delivered — the money is real and the work is live.
      DealStage.won || DealStage.running => Colors.green.shade700,
      // Won and done with: still good, but no longer demanding attention.
      DealStage.completed => Colors.green.shade900,
      DealStage.lost => scheme.error,
      _ => scheme.primary,
    };

class _StageChip extends StatelessWidget {
  const _StageChip({required this.stage});

  final DealStage stage;

  @override
  Widget build(BuildContext context) {
    final color = _stageColor(stage, Theme.of(context).colorScheme);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        stage.label,
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _DealList extends StatelessWidget {
  const _DealList({
    required this.search,
    required this.searchController,
    required this.scope,
    required this.selectedId,
    required this.onSearchChanged,
    required this.onSearchCleared,
    required this.onScopeChanged,
    required this.onSelected,
    required this.dealsAsync,
    required this.onSkipChanged,
  });

  final String search;
  final TextEditingController searchController;
  final _Scope scope;
  final String? selectedId;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onSearchCleared;
  final ValueChanged<_Scope> onScopeChanged;
  final ValueChanged<String> onSelected;
  final AsyncValue<PagedResult<Deal>> dealsAsync;
  final ValueChanged<int> onSkipChanged;

  @override
  Widget build(BuildContext context) {
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
                    hintText: 'Search deals…',
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
                onPressed: () => Navigator.push<Deal>(
                  context,
                  MaterialPageRoute(builder: (_) => const DealFormPage()),
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
                  decoration: const InputDecoration(
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final option in _Scope.values)
                      DropdownMenuItem(value: option, child: Text(option.label)),
                  ],
                  onChanged: (v) => onScopeChanged(v ?? scope),
                ),
              ),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: dealsAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: SelectableText(
                errorText(e),
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
            data: (page) {
              if (page.items.isEmpty) {
                return Center(
                  child: Text(
                    scope == _Scope.onMyPlate ? 'Nothing on your plate.' : 'No deals here.',
                  ),
                );
              }
              return Column(
                children: [
                  Expanded(
                    child: ListView.builder(
                      itemCount: page.items.length,
                      itemBuilder: (context, index) {
                        final deal = page.items[index];
                        final customer = deal.organizationName ?? deal.contactName;
                        return ListTile(
                          selected: deal.id == selectedId,
                          onTap: () => onSelected(deal.id),
                          title: Text(
                            deal.title,
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          subtitle: Text(
                            [
                              ?deal.valueSummary,
                              ?customer,
                              if (deal.expectedCloseDate != null)
                                'by ${_ymd(deal.expectedCloseDate!)}',
                            ].join(' · '),
                          ),
                          trailing: _StageChip(stage: deal.stage),
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

String _ymd(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

class _DealDetail extends ConsumerWidget {
  const _DealDetail({required this.deal});

  final Deal? deal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (deal == null) {
      return const Center(child: Text('Select a deal'));
    }
    final d = deal!;
    final scheme = Theme.of(context).colorScheme;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(d.title, style: Theme.of(context).textTheme.titleLarge),
              ),
              IconButton(
                icon: const Icon(Icons.edit_outlined),
                tooltip: 'Edit',
                onPressed: () => Navigator.push<Deal>(
                  context,
                  MaterialPageRoute(builder: (_) => DealFormPage(deal: d)),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Delete',
                onPressed: () => _confirmDelete(context, ref, d),
              ),
            ],
          ),
          _DealValue(deal: d, color: _stageColor(d.stage, scheme)),
          const SizedBox(height: 16),
          _StageControl(deal: d),
          const SizedBox(height: 8),
          if (d.organizationName != null)
            _Field(label: 'Organization', value: d.organizationName!),
          if (d.contactName != null) _Field(label: 'Contact', value: d.contactName!),
          if (d.expectedCloseDate != null)
            _Field(
              label: d.isOpen ? 'Expected close' : 'Was expected to close',
              value: _ymd(d.expectedCloseDate!),
            ),
          if (d.closedAt != null) _Field(label: 'Closed', value: formatWhen(d.closedAt!)),
          if (d.probability != null) _Field(label: 'Probability', value: '${d.probability}%'),
          if (d.lostReason != null) _Field(label: 'Lost because', value: d.lostReason!),
          if (d.notes != null) _Field(label: 'Notes', value: d.notes!),
          const SizedBox(height: 8),
          // What still has to happen to move this deal along.
          LinkedTasksSection(dealId: d.id),
        ],
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref, Deal d) async {
    final confirmed = await confirmDelete(
      context,
      title: 'Delete deal?',
      message: '"${d.title}" will be permanently deleted.',
    );
    if (!confirmed || !context.mounted) return;
    try {
      await ref.read(dealsRepositoryProvider).delete(d.id);
    } catch (e) {
      if (context.mounted) {
        showErrorSnackBar(context, e, prefix: 'Delete failed.');
      }
      return;
    }
    ref.invalidate(dealsProvider);
  }
}

/// Move the deal along the pipeline.
///
/// Calls the dedicated stage endpoint rather than a PATCH: the server owns what
/// a move implies — the close date, the 100/0 probability, and clearing a lost
/// reason when a deal is reopened.
class _StageControl extends ConsumerStatefulWidget {
  const _StageControl({required this.deal});

  final Deal deal;

  @override
  ConsumerState<_StageControl> createState() => _StageControlState();
}

class _StageControlState extends ConsumerState<_StageControl> {
  bool _moving = false;

  Future<void> _move(DealStage stage) async {
    if (stage == widget.deal.stage) return;

    String? reason;
    if (stage == DealStage.lost) {
      final answer = await _askLostReason(context);
      // Cancelled — the deal stays where it is.
      if (answer == null) return;
      reason = answer.isEmpty ? null : answer;
    }

    setState(() => _moving = true);
    try {
      await ref.read(dealsRepositoryProvider).changeStage(
            widget.deal.id,
            stage,
            lostReason: reason,
          );
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Could not move the deal.');
        setState(() => _moving = false);
      }
      return;
    }
    ref.invalidate(dealsProvider);
    if (mounted) setState(() => _moving = false);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Stage', style: Theme.of(context).textTheme.titleSmall),
            if (_moving) ...[
              const SizedBox(width: 12),
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ],
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final stage in DealStage.values)
              ChoiceChip(
                label: Text(stage.label),
                selected: stage == widget.deal.stage,
                onSelected: _moving ? null : (_) => _move(stage),
                selectedColor: _stageColor(stage, scheme).withValues(alpha: 0.2),
              ),
          ],
        ),
      ],
    );
  }
}

/// Returns the reason, an empty string for "lost, no reason given", or null if
/// the operator backed out.
///
/// The reason is optional on purpose: demanding one behind a modal is how deals
/// end up parked in "negotiation" forever instead of being marked lost.
Future<String?> _askLostReason(BuildContext context) async {
  final controller = TextEditingController();
  try {
    return await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Mark as lost'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Reason (optional)',
            hintText: 'Went with a cheaper agency',
            border: OutlineInputBorder(),
          ),
          onSubmitted: (v) => Navigator.pop(context, v.trim()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Mark as lost'),
          ),
        ],
      ),
    );
  } finally {
    controller.dispose();
  }
}

/// What the deal is worth, in the shape it is actually priced in.
///
/// An open-ended engagement shows its rate and says so, rather than showing
/// nothing — a real deal at a known day rate must not read as an unpriced one.
class _DealValue extends StatelessWidget {
  const _DealValue({required this.deal, required this.color});

  final Deal deal;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final total = deal.formattedExpectedValue;
    final rate = deal.formattedRate;

    if (total == null && rate == null) {
      return Text(
        'No value yet',
        style: theme.textTheme.bodyMedium?.copyWith(color: Colors.grey),
      );
    }

    // The breakdown under the headline: how the total was arrived at, or why
    // there is not one.
    final String? detail;
    if (deal.isOpenEnded) {
      detail = 'Open-ended — no total to forecast';
    } else if (total != null && rate != null && deal.estimatedVolume != null) {
      detail = '$rate × ${deal.estimatedVolume} ${deal.volumeUnit?.plural ?? ''}'.trim();
    } else if (total == null && deal.estimatedVolume != null) {
      // Estimated, but in a unit the rate is not charged in, so multiplying
      // them would need an invented conversion factor.
      detail = 'Estimated in ${deal.volumeUnit?.plural} at a ${deal.rateUnit?.label} rate '
          '— no total derived';
    } else {
      detail = null;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          total ?? rate!,
          style: theme.textTheme.headlineSmall?.copyWith(color: color),
        ),
        if (detail != null)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              detail,
              style: theme.textTheme.bodySmall?.copyWith(color: Colors.grey),
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
