import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/error_text.dart';
import '../models/capture.dart';
import '../providers/captures_provider.dart';
import '../widgets/quick_capture.dart';

/// Where Android's share sheet lands: `/capture?title=…&text=…&url=…`.
///
/// Declared as a `share_target` in web/manifest.json, so "Share → tinyCRM" from
/// the LinkedIn app or Chrome files a person without opening the app first.
/// That is the difference between capturing someone while looking at them and
/// meaning to do it later.
///
/// Saves once, on arrival. Sharing the same thing twice is a thing people do
/// deliberately (two people, one page), so this does not try to be clever about
/// duplicates — [PLAN.md] T-dedupe is where that belongs.
class CaptureSharePage extends ConsumerStatefulWidget {
  const CaptureSharePage({super.key, this.title, this.text, this.url});

  final String? title;
  final String? text;
  final String? url;

  /// The three parameters, composed into the single line the capture box takes.
  ///
  /// Android fills these inconsistently: Chrome sends title + url, some apps
  /// put the url inside `text` and send nothing else. Joining the distinct
  /// non-empty parts handles both without guessing which app is sharing.
  static String composeRaw({String? title, String? text, String? url}) {
    final parts = <String>[];
    for (final part in [title, text, url]) {
      final trimmed = part?.trim() ?? '';
      // `text` frequently repeats the title or the url verbatim.
      if (trimmed.isNotEmpty && !parts.contains(trimmed)) parts.add(trimmed);
    }
    return parts.join(' ');
  }

  @override
  ConsumerState<CaptureSharePage> createState() => _CaptureSharePageState();
}

class _CaptureSharePageState extends ConsumerState<CaptureSharePage> {
  Capture? _saved;
  Object? _error;
  bool _saving = true;

  @override
  void initState() {
    super.initState();
    _save();
  }

  Future<void> _save() async {
    final raw = CaptureSharePage.composeRaw(
      title: widget.title,
      text: widget.text,
      url: widget.url,
    );
    if (raw.isEmpty) {
      setState(() {
        _saving = false;
        _error = 'Nothing was shared.';
      });
      return;
    }

    try {
      final capture = await ref
          .read(capturesRepositoryProvider)
          .create(
            raw,
            // Android already handed over the url, so there is no reason to
            // make the parser find it again in a string we just built.
            url: widget.url?.trim().isEmpty ?? true ? null : widget.url!.trim(),
          );
      if (!mounted) return;
      ref.invalidate(capturesProvider);
      ref.invalidate(newCaptureCountProvider);
      setState(() {
        _saved = capture;
        _saving = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _saving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Captured')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_saving) ...[
                  const Center(child: CircularProgressIndicator()),
                ] else if (_error != null) ...[
                  Icon(Icons.error_outline, size: 48, color: theme.colorScheme.error),
                  const SizedBox(height: 16),
                  Text(
                    _error is String ? _error! as String : errorText(_error!),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: () => showQuickCapture(context),
                    child: const Text('Type it in instead'),
                  ),
                ] else ...[
                  Icon(Icons.check_circle_outline, size: 48, color: theme.colorScheme.primary),
                  const SizedBox(height: 16),
                  Text(
                    _saved!.displayName,
                    style: theme.textTheme.titleLarge,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'In your inbox, waiting to be worked.',
                    style: theme.textTheme.bodyMedium,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    onPressed: () => showQuickCapture(context),
                    child: const Text('Add another'),
                  ),
                  const SizedBox(height: 8),
                  TextButton(
                    onPressed: () => context.go('/inbox'),
                    child: const Text('Open inbox'),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
