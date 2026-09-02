import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../pages/interaction_form_page.dart';
import '../providers/interactions_provider.dart';
import 'interaction_tile.dart';
import 'pagination_bar.dart';

/// "Every call about this deal" — the question contacts-only links could not
/// answer. Also serves organizations and projects.
///
/// Contact detail keeps its own interactions section: that one has existed
/// since interactions did, and filters on the contact link rather than these.
class AttachedInteractionsSection extends ConsumerStatefulWidget {
  const AttachedInteractionsSection({
    super.key,
    this.organizationId,
    this.dealId,
    this.projectId,
    this.padding = EdgeInsets.zero,
  });

  /// Exactly one of these is set — the record whose interactions to list.
  final String? organizationId;
  final String? dealId;
  final String? projectId;

  final EdgeInsetsGeometry padding;

  @override
  ConsumerState<AttachedInteractionsSection> createState() =>
      _AttachedInteractionsSectionState();
}

class _AttachedInteractionsSectionState
    extends ConsumerState<AttachedInteractionsSection> {
  int _skip = 0;

  Future<void> _log() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => InteractionFormPage(
          initialOrganizationId: widget.organizationId,
          initialDealId: widget.dealId,
          initialProjectId: widget.projectId,
        ),
      ),
    );
    // The form invalidates the providers on save; nothing to do here.
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(
      attachedInteractionsProvider((
        organizationId: widget.organizationId,
        dealId: widget.dealId,
        projectId: widget.projectId,
        skip: _skip,
      )),
    );

    return Padding(
      padding: widget.padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Interactions', style: Theme.of(context).textTheme.labelLarge),
              const Spacer(),
              TextButton.icon(
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Log'),
                onPressed: _log,
              ),
            ],
          ),
          async.when(
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
                      'Nothing logged here yet.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  )
                : Column(
                    children: [
                      for (final interaction in page.items)
                        InteractionTile(interaction: interaction, compact: true),
                      PaginationBar(
                        page: page,
                        onSkipChanged: (skip) => setState(() => _skip = skip),
                      ),
                    ],
                  ),
          ),
          const Divider(),
        ],
      ),
    );
  }
}
