import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/date_time_text.dart';
import '../models/contact.dart';
import '../models/interaction.dart';
import '../pages/interaction_form_page.dart';
import '../providers/contacts_provider.dart';
import '../providers/interactions_provider.dart';

class InteractionTile extends ConsumerWidget {
  const InteractionTile({
    super.key,
    required this.interaction,
    this.compact = false,
  });

  final Interaction interaction;

  /// Narrow dashboard column: drop the notes body and the delete button so the
  /// tile still fits at 360px.
  final bool compact;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    // Past and still not confirmed as happened — the one state worth flagging.
    final overdue = interaction.isOverdue;
    final contacts = ref.watch(allContactsProvider).asData?.value ?? <Contact>[];
    final names = contacts
        .where((c) => interaction.contactIds.contains(c.id))
        .map((c) => c.name)
        .toList();

    return Card(
      margin: const EdgeInsets.only(bottom: 4),
      child: ListTile(
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => InteractionFormPage(interaction: interaction),
          ),
        ),
        leading: Icon(
          kindIcons[interaction.kind] ?? Icons.more_horiz,
          color: overdue ? scheme.error : scheme.primary,
        ),
        title: Text(
          interaction.subject,
          style: const TextStyle(fontWeight: FontWeight.w500),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              [
                kindLabels[interaction.kind] ?? interaction.kind,
                formatWhen(interaction.occurredAt),
                if (interaction.durationMinutes != null)
                  '${interaction.durationMinutes} min',
                if (interaction.isPlanned) 'planned',
              ].join(' · '),
              style: TextStyle(color: overdue ? scheme.error : Colors.grey),
            ),
            if (names.isNotEmpty)
              Text(
                names.join(', '),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            if (!compact &&
                interaction.notes != null &&
                interaction.notes!.isNotEmpty)
              MarkdownBody(
                data: interaction.notes!,
                shrinkWrap: true,
                styleSheet: MarkdownStyleSheet.fromTheme(
                  Theme.of(context),
                ).copyWith(p: Theme.of(context).textTheme.bodySmall),
              ),
            if (!compact && interaction.tags.isNotEmpty)
              Wrap(
                spacing: 4,
                children: interaction.tags
                    .map(
                      (t) => Chip(
                        label: Text(t),
                        visualDensity: VisualDensity.compact,
                      ),
                    )
                    .toList(),
              ),
          ],
        ),
        isThreeLine: !compact,
        dense: compact,
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: Icon(
                interaction.done
                    ? Icons.check_circle
                    : Icons.radio_button_unchecked,
                color: interaction.done ? scheme.primary : null,
              ),
              tooltip: interaction.done ? 'Mark as not happened' : 'Mark as happened',
              onPressed: () async {
                await ref
                    .read(interactionsRepositoryProvider)
                    .update(interaction.id, {'done': !interaction.done});
                ref.invalidate(interactionsProvider);
              },
            ),
            if (!compact)
              IconButton(
                icon: const Icon(Icons.delete_outline),
                tooltip: 'Delete',
                onPressed: () async {
                  await ref
                      .read(interactionsRepositoryProvider)
                      .delete(interaction.id);
                  ref.invalidate(interactionsProvider);
                },
              ),
          ],
        ),
      ),
    );
  }
}
