import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';

/// Multi-select over one kind of record: chips for what is linked, a dialog to
/// add another.
///
/// Generalised from the interaction form's contact picker, because documents
/// and interactions now attach to four kinds of record each and eight
/// copy-pasted pickers would drift apart.
class RecordPicker extends StatelessWidget {
  const RecordPicker({
    super.key,
    required this.label,
    required this.addLabel,
    required this.emptyLabel,
    required this.optionsAsync,
    required this.selectedIds,
    required this.onChanged,
  });

  final String label;

  /// "Link deal" — what the add button says.
  final String addLabel;
  final String emptyLabel;

  /// Every option, as id → what to show for it.
  final AsyncValue<Map<String, String>> optionsAsync;
  final List<String> selectedIds;
  final ValueChanged<List<String>> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: optionsAsync.when(
        loading: () => const LinearProgressIndicator(),
        error: (e, _) => Text('Could not load $label. ${errorText(e)}'),
        data: (options) {
          // Only ids that still exist — a record deleted elsewhere would
          // otherwise render as a chip with no label.
          final selected = selectedIds.where(options.containsKey).toList();
          final available = options.keys.where((id) => !selected.contains(id)).toList();

          return InputDecorator(
            decoration: InputDecoration(
              labelText: label,
              border: const OutlineInputBorder(),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (selected.isEmpty)
                  Text(emptyLabel, style: const TextStyle(color: Colors.grey))
                else
                  Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: [
                      for (final id in selected)
                        InputChip(
                          label: Text(options[id]!),
                          deleteIcon: const Icon(Icons.close, size: 16),
                          onDeleted: () =>
                              onChanged(selectedIds.where((s) => s != id).toList()),
                          visualDensity: VisualDensity.compact,
                        ),
                    ],
                  ),
                if (available.isNotEmpty)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      icon: const Icon(Icons.add, size: 18),
                      label: Text(addLabel),
                      onPressed: () async {
                        final picked = await showDialog<String>(
                          context: context,
                          builder: (ctx) => SimpleDialog(
                            title: Text(addLabel),
                            children: [
                              for (final id in available)
                                SimpleDialogOption(
                                  onPressed: () => Navigator.pop(ctx, id),
                                  child: Text(options[id]!),
                                ),
                            ],
                          ),
                        );
                        if (picked == null) return;
                        onChanged([...selected, picked]);
                      },
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}
