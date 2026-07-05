import 'dart:js_interop';
import 'dart:typed_data';

import 'package:web/web.dart' as web;

/// MIME type sent to the browser for a stored document [format]
/// (`pdf` / `markdown` / `txt`).
String mimeTypeForFormat(String format) {
  return switch (format) {
    'pdf' => 'application/pdf',
    'markdown' => 'text/markdown',
    _ => 'text/plain',
  };
}

/// File extension used when saving a document of the given [format].
String extensionForFormat(String format) {
  return {'pdf': 'pdf', 'markdown': 'md', 'txt': 'txt'}[format] ?? 'bin';
}

/// Triggers a browser "Save as" for [bytes] under [filename].
///
/// The bytes are handed to [web.Blob] as a typed array (BufferSource). If we
/// pass a JS array of plain numbers instead, each byte is coerced to its
/// decimal string, producing a file that contains only the digits 0-9 (#51).
void downloadBytesToBrowser(List<int> bytes, String filename, String mimeType) {
  final data = Uint8List.fromList(bytes);
  final blob = web.Blob([data.toJS].toJS, web.BlobPropertyBag(type: mimeType));
  final url = web.URL.createObjectURL(blob);
  final anchor = web.document.createElement('a') as web.HTMLAnchorElement;
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  web.URL.revokeObjectURL(url);
}
