import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/error_text.dart';
import '../models/document.dart';
import '../providers/documents_provider.dart';
import 'pagination_bar.dart';

/// Everything filed against one record — the contract on a deal, the NDA on a
/// contact. Documents could only belong to a project before this.
class AttachedDocumentsSection extends ConsumerStatefulWidget {
  const AttachedDocumentsSection({
    super.key,
    this.contactId,
    this.organizationId,
    this.dealId,
    this.projectId,
    this.padding = EdgeInsets.zero,
  });

  /// Exactly one of these is set — the record whose documents to list.
  final String? contactId;
  final String? organizationId;
  final String? dealId;
  final String? projectId;

  final EdgeInsetsGeometry padding;

  @override
  ConsumerState<AttachedDocumentsSection> createState() =>
      _AttachedDocumentsSectionState();
}

class _AttachedDocumentsSectionState
    extends ConsumerState<AttachedDocumentsSection> {
  int _skip = 0;

  static const _formatIcons = {
    'pdf': Icons.picture_as_pdf_outlined,
    'markdown': Icons.article_outlined,
    'txt': Icons.description_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(
      attachedDocumentsProvider((
        contactId: widget.contactId,
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
          Text('Documents', style: Theme.of(context).textTheme.labelLarge),
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
                      'Nothing filed here yet.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  )
                : Column(
                    children: [
                      for (final doc in page.items)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          dense: true,
                          leading: Icon(
                            _formatIcons[doc.format] ?? Icons.insert_drive_file_outlined,
                          ),
                          title: Text(doc.title),
                          subtitle: Text(_subtitle(doc)),
                        ),
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

  /// Format and size, plus a note when the same file is filed elsewhere too —
  /// so deleting it is visibly not a local decision.
  String _subtitle(Document doc) {
    final elsewhere = doc.linkCount - 1;
    return [
      doc.format.toUpperCase(),
      '${(doc.size / 1024).ceil()} KB',
      if (elsewhere > 0)
        elsewhere == 1 ? 'also filed elsewhere' : 'also filed under $elsewhere others',
    ].join(' · ');
  }
}
