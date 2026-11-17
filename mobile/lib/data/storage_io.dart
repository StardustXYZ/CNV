import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'storage.dart';

TextStorage deviceStorage() => FileStorage(getApplicationSupportDirectory);

Future<String?> oldWebVotes() async => null;

/// One file per text, in the app's own folder on the phone.
class FileStorage implements TextStorage {
  FileStorage(this._folder);

  final Future<Directory> Function() _folder;

  Future<File> _file(String name) async => File('${(await _folder()).path}${Platform.pathSeparator}$name');

  @override
  Future<String?> read(String name) async {
    try {
      final file = await _file(name);
      return await file.exists() ? await file.readAsString() : null;
    } catch (err) {
      debugPrint('$name non leggibile: $err');
      return null;
    }
  }

  @override
  Future<void> write(String name, String text) async => (await _file(name)).writeAsString(text, flush: true);
}
