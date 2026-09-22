import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/capture.dart';
import '../providers/captures_provider.dart';

/// Opens the quick-add box. One line in, nothing else required.
Future<void> showQuickCapture(BuildContext context, {String? initialText}) {
  return showDialog<void>(
    context: context,
    builder: (_) => _QuickCaptureDialog(initialText: initialText),
  );
}

/// The always-available capture affordance in the app bar.
///
/// Present in both the wide and the narrow layout: the whole feature is worth
/// nothing if putting something in is ever more than one tap away.
class QuickCaptureButton extends StatelessWidget {
  const QuickCaptureButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      onPressed: () => showQuickCapture(context),
      icon: const Icon(Icons.bolt_outlined),
      tooltip: 'Quick capture',
    );
  }
}

/// A single autofocused field that clears and keeps focus after each save.
///
/// Built for the real motion: you are looking at a list of people and want to
/// put four of them somewhere in ten seconds. Closing the dialog after one save
/// would turn that into four round trips through the app bar, so the dialog
/// stays open and the field stays hot.
class _QuickCaptureDialog extends ConsumerStatefulWidget {
  const _QuickCaptureDialog({this.initialText});

  final String? initialText;

  @override
  ConsumerState<_QuickCaptureDialog> createState() => _QuickCaptureDialogState();
}

class _QuickCaptureDialogState extends ConsumerState<_QuickCaptureDialog> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.initialText ?? '',
  );
  final _noteController = TextEditingController();
  final _focus = FocusNode();

  /// Saved in this sitting, newest first — so Undo has something to point at
  /// and the count is visible without leaving the dialog.
  final List<Capture> _saved = [];
  bool _saving = false;
  bool _noteOpen = false;

  @override
  void dispose() {
    _controller.dispose();
    _noteController.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final raw = _controller.text.trim();
    // Enter on an empty field is a no-op rather than an error: it is what
    // happens when someone taps Enter twice.
    if (raw.isEmpty || _saving) return;

    setState(() => _saving = true);
    final note = _noteController.text.trim();
    try {
      final capture = await ref
          .read(capturesRepositoryProvider)
          .create(raw, note: note.isEmpty ? null : note);
      if (!mounted) return;
      setState(() {
        _saved.insert(0, capture);
        _controller.clear();
        _noteController.clear();
        _saving = false;
      });
      // Straight back to typing the next one.
      _focus.requestFocus();
    } catch (e) {
      if (!mounted) return;
      showErrorSnackBar(context, e, prefix: 'Could not save.');
      // The text stays put, so a failed save never loses what was typed.
      setState(() => _saving = false);
    }
  }

  Future<void> _undo(Capture capture) async {
    try {
      await ref.read(capturesRepositoryProvider).delete(capture.id);
      if (!mounted) return;
      setState(() => _saved.remove(capture));
    } catch (e) {
      if (!mounted) return;
      showErrorSnackBar(context, e, prefix: 'Could not undo.');
    }
  }

  void _close() {
    // Only now, so the inbox and the badge are refreshed once rather than on
    // every keystroke-sized save.
    if (_saved.isNotEmpty) {
      ref.invalidate(capturesProvider);
      ref.invalidate(newCaptureCountProvider);
    }
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return AlertDialog(
      title: const Text('Quick capture'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_saved.isNotEmpty) ...[
              // Newest at the top, next to the field, where it can be undone
              // without hunting.
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 180),
                child: ListView(
                  shrinkWrap: true,
                  children: [
                    for (final capture in _saved)
                      ListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(Icons.check, size: 18, color: scheme.primary),
                        title: Text(
                          capture.displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        trailing: TextButton(
                          onPressed: () => _undo(capture),
                          child: const Text('Undo'),
                        ),
                      ),
                  ],
                ),
              ),
              const Divider(),
            ],
            TextField(
              controller: _controller,
              focusNode: _focus,
              autofocus: true,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _save(),
              decoration: const InputDecoration(
                labelText: 'Name or link',
                hintText: 'Jane Doe — or a profile URL',
                helperText: 'Enter saves and clears. Paste several in a row.',
              ),
            ),
            if (_noteOpen)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: TextField(
                  controller: _noteController,
                  maxLines: 2,
                  decoration: const InputDecoration(
                    labelText: 'Note',
                    hintText: 'Where they came from, why they are worth writing to',
                  ),
                ),
              )
            else
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () => setState(() => _noteOpen = true),
                  icon: const Icon(Icons.notes, size: 18),
                  label: const Text('Add a note'),
                ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : _close,
          child: Text(_saved.isEmpty ? 'Cancel' : 'Done (${_saved.length})'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: const Text('Save'),
        ),
      ],
    );
  }
}
