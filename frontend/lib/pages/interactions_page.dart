import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/interaction.dart';
import '../providers/interactions_provider.dart';
import '../widgets/interaction_tile.dart';
import '../widgets/pagination_bar.dart';
import 'interaction_form_page.dart';

/// Activity log: what is planned on the left, what already happened on the
/// right — both are Interactions, split by whether occurred_at is in the future.
class InteractionsPage extends ConsumerStatefulWidget {
  const InteractionsPage({super.key});

  @override
  ConsumerState<InteractionsPage> createState() => _InteractionsPageState();
}

class _InteractionsPageState extends ConsumerState<InteractionsPage> {
  final _searchController = TextEditingController();
  String _search = '';
  String? _kind;
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final planned = _Panel(
      title: 'Planned',
      emptyText: 'Nothing planned.',
      search: _search,
      kind: _kind,
      upcoming: true,
    );
    final log = _Panel(
      title: 'Activity log',
      emptyText: 'No interactions logged yet.',
      search: _search,
      kind: _kind,
      upcoming: false,
    );

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _searchController,
                  decoration: InputDecoration(
                    hintText: 'Search interactions…',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: _search.isEmpty
                        ? null
                        : IconButton(
                            icon: const Icon(Icons.clear),
                            onPressed: () {
                              _debounce?.cancel();
                              _searchController.clear();
                              setState(() => _search = '');
                            },
                          ),
                    isDense: true,
                    border: const OutlineInputBorder(),
                  ),
                  onChanged: (v) {
                    _debounce?.cancel();
                    _debounce = Timer(const Duration(seconds: 1), () {
                      setState(() => _search = v.trim());
                    });
                  },
                ),
              ),
              const SizedBox(width: 12),
              DropdownButton<String?>(
                value: _kind,
                hint: const Text('All kinds'),
                underline: const SizedBox.shrink(),
                onChanged: (k) => setState(() => _kind = k),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('All kinds'),
                  ),
                  for (final k in interactionKinds)
                    DropdownMenuItem<String?>(
                      value: k,
                      child: Text(kindLabels[k]!),
                    ),
                ],
              ),
              IconButton(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => const InteractionFormPage(),
                  ),
                ),
                icon: const Icon(Icons.add),
                tooltip: 'New Interaction',
              ),
            ],
          ),
        ),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              if (constraints.maxWidth >= 700) {
                return Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(width: 360, child: planned),
                      const SizedBox(width: 16),
                      Expanded(child: log),
                    ],
                  ),
                );
              }
              return DefaultTabController(
                length: 2,
                child: Column(
                  children: [
                    Expanded(child: TabBarView(children: [planned, log])),
                    const TabBar(
                      tabs: [
                        Tab(icon: Icon(Icons.event_outlined), text: 'Planned'),
                        Tab(icon: Icon(Icons.history), text: 'Log'),
                      ],
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _Panel extends ConsumerStatefulWidget {
  const _Panel({
    required this.title,
    required this.emptyText,
    required this.search,
    required this.kind,
    required this.upcoming,
  });

  final String title;
  final String emptyText;
  final String search;
  final String? kind;
  final bool upcoming;

  @override
  ConsumerState<_Panel> createState() => _PanelState();
}

class _PanelState extends ConsumerState<_Panel> {
  int _skip = 0;

  @override
  void didUpdateWidget(_Panel oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A new query means the old offset is meaningless — back to page 1.
    if (oldWidget.search != widget.search || oldWidget.kind != widget.kind) {
      _skip = 0;
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(
      interactionsProvider((
        search: widget.search,
        contactId: null,
        kind: widget.kind,
        upcoming: widget.upcoming,
        skip: _skip,
      )),
    );

    return Card(
      margin: EdgeInsets.zero,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                widget.title,
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: async.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(
                child: SelectableText(
                  errorText(e),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
              data: (page) => page.items.isEmpty
                  ? Center(child: Text(widget.emptyText))
                  : Column(
                      children: [
                        Expanded(
                          child: ListView.builder(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            itemCount: page.items.length,
                            itemBuilder: (context, index) => InteractionTile(
                              interaction: page.items[index],
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
          ),
        ],
      ),
    );
  }
}
