import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../core/web_download.dart';
import '../models/capture.dart';
import '../models/paged_result.dart';
import '../providers/captures_provider.dart';
import '../providers/contacts_provider.dart';
import '../providers/deals_provider.dart';
import '../providers/interactions_provider.dart';
import '../providers/organizations_provider.dart';
import '../widgets/confirm_dialog.dart';
import '../widgets/pagination_bar.dart';

/// What the list is showing. Defaults to [waiting] — working the backlog is the
/// reason the screen exists, and everything else is looking things up.
enum _Scope {
  waiting('Waiting', CaptureStatus.isNew),
  converted('Converted', CaptureStatus.converted),
  dismissed('Dismissed', CaptureStatus.dismissed),
  everything('All', null);

  const _Scope(this.label, this.status);

  final String label;

  /// null means every status.
  final CaptureStatus? status;
}

/// The inbox: names and links parked earlier, worked one at a time.
///
/// Oldest first, and the detail pane advances to the next item the moment one
/// is converted — this is meant to be a session you grind through, not a form
/// you open once.
class InboxPage extends ConsumerStatefulWidget {
  const InboxPage({super.key});

  @override
  ConsumerState<InboxPage> createState() => _InboxPageState();
}

class _InboxPageState extends ConsumerState<InboxPage> with SingleTickerProviderStateMixin {
  final _searchController = TextEditingController();
  String _search = '';
  _Scope _scope = _Scope.waiting;
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

  /// Move to the item after [workedId], so converting one lands straight on the
  /// next. Falls back to the one before it at the end of the list, and to
  /// nothing at all when the inbox is empty.
  ///
  /// Computed from the page that was on screen *before* the refresh, because
  /// the worked capture is about to disappear from it and there would be
  /// nothing left to take a position from.
  void _advancePast(String workedId, List<Capture> shownBefore) {
    final index = shownBefore.indexWhere((c) => c.id == workedId);
    String? next;
    if (index != -1) {
      if (index + 1 < shownBefore.length) {
        next = shownBefore[index + 1].id;
      } else if (index > 0) {
        next = shownBefore[index - 1].id;
      }
    }
    setState(() => _selectedId = next);
  }

  void _refreshAfterTriage() {
    ref.invalidate(capturesProvider);
    ref.invalidate(newCaptureCountProvider);
  }

  @override
  Widget build(BuildContext context) {
    final capturesAsync = ref.watch(
      capturesProvider((status: _scope.status, search: _search, skip: _skip)),
    );

    Widget detail() => capturesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(errorText(e))),
      data: (page) {
        final capture = _selectedId == null
            ? null
            : page.items.where((c) => c.id == _selectedId).firstOrNull;
        return _TriagePanel(
          capture: capture,
          remaining: page.total,
          onWorked: (id) {
            _advancePast(id, page.items);
            _refreshAfterTriage();
          },
        );
      },
    );

    Widget list({VoidCallback? onNarrow}) => _CaptureList(
      searchController: _searchController,
      scope: _scope,
      selectedId: _selectedId,
      capturesAsync: capturesAsync,
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
        _selectedId = null;
      }),
      onSelected: (id) {
        setState(() => _selectedId = id);
        onNarrow?.call();
      },
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
                children: [list(onNarrow: () => _tabController.animateTo(1)), detail()],
              ),
            ),
            TabBar(
              controller: _tabController,
              tabs: const [
                Tab(icon: Icon(Icons.inbox_outlined), text: 'Inbox'),
                Tab(icon: Icon(Icons.how_to_reg_outlined), text: 'Triage'),
              ],
            ),
          ],
        );
      },
    );
  }
}

class _CaptureList extends StatelessWidget {
  const _CaptureList({
    required this.searchController,
    required this.scope,
    required this.selectedId,
    required this.capturesAsync,
    required this.onSearchChanged,
    required this.onSearchCleared,
    required this.onScopeChanged,
    required this.onSelected,
    required this.onSkipChanged,
  });

  final TextEditingController searchController;
  final _Scope scope;
  final String? selectedId;
  final AsyncValue<PagedResult<Capture>> capturesAsync;
  final ValueChanged<String> onSearchChanged;
  final VoidCallback onSearchCleared;
  final ValueChanged<_Scope> onScopeChanged;
  final ValueChanged<String> onSelected;
  final ValueChanged<int> onSkipChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
          child: TextField(
            controller: searchController,
            onChanged: onSearchChanged,
            decoration: InputDecoration(
              labelText: 'Search',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: searchController.text.isEmpty
                  ? null
                  : IconButton(
                      onPressed: onSearchCleared,
                      icon: const Icon(Icons.clear),
                      tooltip: 'Clear',
                    ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
          child: DropdownButtonFormField<_Scope>(
            initialValue: scope,
            decoration: const InputDecoration(labelText: 'Show'),
            items: [
              for (final option in _Scope.values)
                DropdownMenuItem(value: option, child: Text(option.label)),
            ],
            onChanged: (value) => value == null ? null : onScopeChanged(value),
          ),
        ),
        Expanded(
          child: capturesAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text(errorText(e))),
            data: (page) {
              if (page.items.isEmpty) {
                return Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      scope == _Scope.waiting
                          ? 'Nothing waiting. Capture a name or a link with the bolt in the app bar.'
                          : 'Nothing here.',
                      textAlign: TextAlign.center,
                    ),
                  ),
                );
              }
              return ListView.builder(
                itemCount: page.items.length,
                itemBuilder: (context, index) {
                  final capture = page.items[index];
                  return _CaptureTile(
                    capture: capture,
                    selected: capture.id == selectedId,
                    onTap: () => onSelected(capture.id),
                  );
                },
              );
            },
          ),
        ),
        capturesAsync.maybeWhen(
          data: (page) => PaginationBar(page: page, onSkipChanged: onSkipChanged),
          orElse: () => const SizedBox.shrink(),
        ),
      ],
    );
  }
}

class _CaptureTile extends StatelessWidget {
  const _CaptureTile({required this.capture, required this.selected, required this.onTap});

  final Capture capture;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final waiting = capture.daysWaiting;

    final subtitle = <String>[
      if (capture.url != null) Uri.tryParse(capture.url!)?.host ?? capture.url!,
      if (capture.note != null && capture.note!.isNotEmpty) capture.note!,
      // The age is what turns a list into a nudge. Silent on the day it was
      // captured — "waiting 0 days" is noise.
      if (capture.isOpen && waiting == 1) 'waiting 1 day',
      if (capture.isOpen && waiting > 1) 'waiting $waiting days',
      if (capture.status == CaptureStatus.converted && capture.contactName != null)
        'became ${capture.contactName}',
    ].join(' · ');

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      color: selected ? scheme.primaryContainer : null,
      child: ListTile(
        onTap: onTap,
        leading: Icon(
          capture.url == null ? Icons.person_outline : Icons.link,
          color: scheme.primary,
        ),
        title: Text(capture.displayName, maxLines: 1, overflow: TextOverflow.ellipsis),
        subtitle: subtitle.isEmpty
            ? null
            : Text(subtitle, maxLines: 2, overflow: TextOverflow.ellipsis),
      ),
    );
  }
}

/// The triage panel: one capture, everything needed to turn it into a lead.
///
/// One scroll and no tabs on purpose. Every extra click here is paid once per
/// person in the backlog, which is the cost that stops a session happening at
/// all.
class _TriagePanel extends ConsumerStatefulWidget {
  const _TriagePanel({required this.capture, required this.remaining, required this.onWorked});

  final Capture? capture;
  final int remaining;

  /// Called with the id of the capture that was just converted or dismissed.
  final ValueChanged<String> onWorked;

  @override
  ConsumerState<_TriagePanel> createState() => _TriagePanelState();
}

class _TriagePanelState extends ConsumerState<_TriagePanel> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _jobTitleController = TextEditingController();
  final _websiteController = TextEditingController();
  final _dealTitleController = TextEditingController();
  final _subjectController = TextEditingController();
  final _messageNotesController = TextEditingController();

  String? _existingContactId;
  String? _organizationId;
  bool _openDeal = true;
  bool _logOutreach = true;
  bool _saving = false;

  List<TextEditingController> get _controllers => [
    _nameController,
    _emailController,
    _jobTitleController,
    _websiteController,
    _dealTitleController,
    _subjectController,
    _messageNotesController,
  ];

  @override
  void initState() {
    super.initState();
    _prefill();
  }

  @override
  void didUpdateWidget(_TriagePanel old) {
    super.didUpdateWidget(old);
    // A different capture means a different person — never carry one person's
    // half-typed email onto the next one in the queue.
    if (old.capture?.id != widget.capture?.id) {
      _prefill();
    }
  }

  @override
  void dispose() {
    for (final controller in _controllers) {
      controller.dispose();
    }
    super.dispose();
  }

  void _prefill() {
    final capture = widget.capture;
    final name = capture?.name ?? '';
    _existingContactId = null;
    _organizationId = null;
    _openDeal = true;
    _logOutreach = true;
    _nameController.text = name;
    _emailController.clear();
    _jobTitleController.clear();
    // The captured link is almost always the person's profile.
    _websiteController.text = capture?.url ?? '';
    _dealTitleController.text = name.isEmpty ? 'Outreach' : 'Outreach – $name';
    _subjectController.text = name.isEmpty ? 'Wrote to them' : 'Wrote to $name';
    _messageNotesController.clear();
  }

  Future<void> _convert() async {
    final capture = widget.capture;
    if (capture == null || _saving) return;
    if (!_formKey.currentState!.validate()) return;

    setState(() => _saving = true);
    final name = _nameController.text.trim();
    try {
      final result = await ref
          .read(capturesRepositoryProvider)
          .convert(
            capture.id,
            contactId: _existingContactId,
            contact: _existingContactId != null
                ? null
                : <String, dynamic>{
                    'name': name,
                    'job_title': ?_textOrNull(_jobTitleController),
                    'email': ?_textOrNull(_emailController),
                    'website': ?_textOrNull(_websiteController),
                    'organization_id': ?_organizationId,
                    'lifecycle_status': 'lead',
                  },
            deal: _openDeal
                ? <String, dynamic>{'title': _dealTitleController.text.trim()}
                : null,
            interaction: _logOutreach
                ? <String, dynamic>{
                    'kind': 'email',
                    'subject': _subjectController.text.trim(),
                    'notes': ?_textOrNull(_messageNotesController),
                  }
                : null,
          );
      if (!mounted) return;
      // Everything the convert touched, so no screen shows a stale count.
      ref.invalidate(contactsProvider);
      ref.invalidate(allContactsProvider);
      ref.invalidate(organizationsProvider);
      if (result.openedDeal) ref.invalidate(dealsProvider);
      if (result.loggedOutreach) ref.invalidate(interactionsProvider);

      setState(() => _saving = false);
      widget.onWorked(capture.id);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result.openedDeal
                ? '${result.contactName} is a lead. ${widget.remaining - 1} left.'
                : '${result.contactName} filed. ${widget.remaining - 1} left.',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      showErrorSnackBar(context, e, prefix: 'Could not convert.');
      setState(() => _saving = false);
    }
  }

  Future<void> _dismiss() async {
    final capture = widget.capture;
    if (capture == null || _saving) return;
    final confirmed = await confirmDelete(
      context,
      title: 'Dismiss this capture?',
      message:
          '${capture.displayName} stays on record as decided against, so the '
          'inbox will not offer it again.',
      confirmLabel: 'Dismiss',
    );
    if (!confirmed || !mounted) return;

    setState(() => _saving = true);
    try {
      await ref.read(capturesRepositoryProvider).dismiss(capture.id);
      if (!mounted) return;
      setState(() => _saving = false);
      widget.onWorked(capture.id);
    } catch (e) {
      if (!mounted) return;
      showErrorSnackBar(context, e, prefix: 'Could not dismiss.');
      setState(() => _saving = false);
    }
  }

  String? _textOrNull(TextEditingController controller) {
    final text = controller.text.trim();
    return text.isEmpty ? null : text;
  }

  @override
  Widget build(BuildContext context) {
    final capture = widget.capture;
    if (capture == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Pick something from the inbox to work on it.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    if (!capture.isOpen) {
      return _WorkedSummary(capture: capture);
    }

    final contactOptions = ref
        .watch(allContactsProvider)
        .whenData((contacts) => {for (final c in contacts) c.id: c.name});
    final organizationOptions = ref
        .watch(allOrganizationsProvider)
        .whenData((orgs) => {for (final o in orgs) o.id: o.name});

    return Form(
      key: _formKey,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _CaptureHeader(capture: capture),
          const SizedBox(height: 16),

          _SectionTitle('Who they are'),
          // Linking an existing person rather than creating a duplicate — the
          // "I already know them" case, which is common enough to be offered
          // rather than discovered afterwards.
          contactOptions.when(
            loading: () => const LinearProgressIndicator(),
            error: (e, _) => Text('Could not load contacts. ${errorText(e)}'),
            data: (options) => DropdownButtonFormField<String?>(
              // `initialValue` is read once per form-field state, so the reset
              // in _prefill() would not reach a field that stays mounted from
              // one capture to the next: the previous person would still be
              // shown while a new one was submitted. Keying on the capture
              // forces a fresh field for each.
              key: ValueKey('contact-${capture.id}'),
              initialValue: _existingContactId,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Contact',
                helperText: 'Leave as a new person unless you already have them',
              ),
              items: [
                const DropdownMenuItem<String?>(value: null, child: Text('New person')),
                for (final entry in options.entries)
                  DropdownMenuItem<String?>(
                    value: entry.key,
                    child: Text(entry.value, overflow: TextOverflow.ellipsis),
                  ),
              ],
              onChanged: _saving ? null : (value) => setState(() => _existingContactId = value),
            ),
          ),
          if (_existingContactId == null) ...[
            const SizedBox(height: 12),
            TextFormField(
              controller: _nameController,
              decoration: const InputDecoration(labelText: 'Name *'),
              validator: (value) =>
                  (value == null || value.trim().isEmpty) ? 'A name is required' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _jobTitleController,
              decoration: const InputDecoration(
                labelText: 'Job title',
                helperText: 'Half of whether an approach is worth making',
              ),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _emailController,
              decoration: const InputDecoration(labelText: 'Email'),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _websiteController,
              decoration: const InputDecoration(labelText: 'Website or profile'),
            ),
            const SizedBox(height: 12),
            organizationOptions.when(
              loading: () => const LinearProgressIndicator(),
              error: (e, _) => Text('Could not load organizations. ${errorText(e)}'),
              data: (options) => DropdownButtonFormField<String?>(
                key: ValueKey('organization-${capture.id}'),
                initialValue: _organizationId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Organization'),
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('None')),
                  for (final entry in options.entries)
                    DropdownMenuItem<String?>(
                      value: entry.key,
                      child: Text(entry.value, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: _saving ? null : (value) => setState(() => _organizationId = value),
              ),
            ),
          ],

          const SizedBox(height: 24),
          _SectionTitle('The lead'),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _openDeal,
            onChanged: _saving ? null : (value) => setState(() => _openDeal = value),
            title: const Text('Open a deal at stage Lead'),
            subtitle: const Text('Puts them on the pipeline board'),
          ),
          if (_openDeal)
            TextFormField(
              controller: _dealTitleController,
              decoration: const InputDecoration(labelText: 'Deal title *'),
              validator: (value) => (_openDeal && (value == null || value.trim().isEmpty))
                  ? 'A deal needs a title'
                  : null,
            ),

          const SizedBox(height: 24),
          _SectionTitle('I wrote to them'),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            value: _logOutreach,
            onChanged: _saving ? null : (value) => setState(() => _logOutreach = value),
            title: const Text('Log the message'),
            subtitle: const Text('Recorded as happening now, in the activity log'),
          ),
          if (_logOutreach) ...[
            TextFormField(
              controller: _subjectController,
              decoration: const InputDecoration(labelText: 'Subject *'),
              validator: (value) => (_logOutreach && (value == null || value.trim().isEmpty))
                  ? 'The log entry needs a subject'
                  : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _messageNotesController,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'Notes',
                hintText: 'What you said, what you asked for',
              ),
            ),
          ],

          const SizedBox(height: 24),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _saving ? null : _convert,
                  icon: const Icon(Icons.arrow_forward),
                  label: Text(_saving ? 'Working…' : 'Convert and go to next'),
                ),
              ),
              const SizedBox(width: 12),
              TextButton(
                onPressed: _saving ? null : _dismiss,
                child: const Text('Dismiss'),
              ),
            ],
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }
}

class _CaptureHeader extends StatelessWidget {
  const _CaptureHeader({required this.capture});

  final Capture capture;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final waiting = capture.daysWaiting;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(capture.displayName, style: theme.textTheme.titleLarge),
            const SizedBox(height: 4),
            // What was actually typed, always shown: the parsed name above it
            // is a guess, and this is how a wrong one gets noticed.
            Text(capture.raw, style: theme.textTheme.bodySmall),
            if (capture.note != null && capture.note!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(capture.note!),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (capture.url != null)
                  // Same affordance as "Open & sweep" on /watches: look at the
                  // person before deciding anything about them.
                  FilledButton.tonalIcon(
                    onPressed: () => openInNewTab(capture.url!),
                    icon: const Icon(Icons.open_in_new, size: 18),
                    label: const Text('Open link'),
                  ),
                Text(
                  waiting == 0
                      ? 'Captured today'
                      : waiting == 1
                      ? 'Captured yesterday'
                      : 'Captured $waiting days ago',
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// What a capture became, once it has been worked.
class _WorkedSummary extends StatelessWidget {
  const _WorkedSummary({required this.capture});

  final Capture capture;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _CaptureHeader(capture: capture),
        const SizedBox(height: 16),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(capture.status.label, style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                if (capture.contactName != null) Text('Person: ${capture.contactName}'),
                if (capture.dealTitle != null) Text('Lead: ${capture.dealTitle}'),
                if (capture.status == CaptureStatus.dismissed)
                  const Text('Decided against. The inbox will not offer it again.'),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(text, style: Theme.of(context).textTheme.titleMedium),
    );
  }
}
