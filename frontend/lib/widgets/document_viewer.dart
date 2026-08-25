import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:pdfrx/pdfrx.dart';

import '../core/web_download.dart';
import '../core/error_text.dart';
import '../models/document.dart';
import '../providers/documents_provider.dart';

/// Opens a full-screen viewer that renders [doc] inline (PDF, Markdown or
/// plain text) without downloading it to disk.
void showDocumentViewer(BuildContext context, Document doc) {
  showDialog<void>(
    context: context,
    barrierColor: Colors.black87,
    builder: (_) => Dialog.fullscreen(child: _DocumentViewer(doc: doc)),
  );
}

class _DocumentViewer extends ConsumerStatefulWidget {
  const _DocumentViewer({required this.doc});

  final Document doc;

  @override
  ConsumerState<_DocumentViewer> createState() => _DocumentViewerState();
}

class _DocumentViewerState extends ConsumerState<_DocumentViewer> {
  late Future<Uint8List> _bytes;

  @override
  void initState() {
    super.initState();
    _bytes = ref
        .read(documentsRepositoryProvider)
        .downloadBytes(widget.doc.id);
  }

  Future<void> _download() async {
    try {
      final bytes = await _bytes;
      downloadBytesToBrowser(
        bytes,
        '${widget.doc.title}.${extensionForFormat(widget.doc.format)}',
        mimeTypeForFormat(widget.doc.format),
      );
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, e, prefix: 'Download failed.');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.doc.title, overflow: TextOverflow.ellipsis),
        leading: IconButton(
          icon: const Icon(Icons.close),
          tooltip: 'Close',
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.download),
            tooltip: 'Download',
            onPressed: _download,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: FutureBuilder<Uint8List>(
        future: _bytes,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || snapshot.data == null) {
            return Center(
              child: SelectableText(
                'Could not load document: ${snapshot.error}',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            );
          }
          return _content(snapshot.data!);
        },
      ),
    );
  }

  Widget _content(Uint8List bytes) {
    switch (widget.doc.format) {
      case 'pdf':
        return PdfViewer.data(bytes, sourceName: widget.doc.id);
      case 'markdown':
        return Markdown(
          data: _decode(bytes),
          selectable: true,
          padding: const EdgeInsets.all(24),
        );
      default:
        return SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: SelectableText(
            _decode(bytes),
            style: const TextStyle(fontFamily: 'monospace', height: 1.4),
          ),
        );
    }
  }

  String _decode(Uint8List bytes) => utf8.decode(bytes, allowMalformed: true);
}
