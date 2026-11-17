import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// Makes the file and opens the share menu (Drive, email, Files…), where it can be saved.
Future<void> saveTextFile(String name, String content, String mime) async {
  final file = File('${(await getTemporaryDirectory()).path}${Platform.pathSeparator}$name');
  await file.writeAsString(content, flush: true);
  await SharePlus.instance.share(ShareParams(files: [XFile(file.path, mimeType: mime)], subject: name));
}
