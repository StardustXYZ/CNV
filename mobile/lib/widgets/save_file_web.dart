import 'dart:convert';
import 'dart:js_interop';

import 'package:web/web.dart' as web;

/// Downloads the file, as any download of the browser.
Future<void> saveTextFile(String name, String content, String mime) async {
  final bytes = utf8.encode(content);
  final blob = web.Blob([bytes.toJS].toJS, web.BlobPropertyBag(type: '$mime;charset=utf-8'));
  final url = web.URL.createObjectURL(blob);
  final link = web.HTMLAnchorElement()
    ..href = url
    ..download = name;
  web.document.body?.append(link);
  link.click();
  link.remove();
  web.URL.revokeObjectURL(url);
}
