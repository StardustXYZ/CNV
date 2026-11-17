/// Small texts the app keeps on the device: files on the phone, the browser's own storage
/// on the web (the same code runs in both).
library;

import 'storage_io.dart' if (dart.library.js_interop) 'storage_web.dart' as device;

abstract class TextStorage {
  /// The saved text, or null when there is none (or it cannot be read).
  Future<String?> read(String name);

  Future<void> write(String name, String text);
}

/// Where this device keeps the app's texts.
TextStorage deviceStorage() => device.deviceStorage();

/// In the browser: the votes of the old web version of CNV, saved at the same address, as a
/// copy of the votes ({"votes", "seen", "exported", "diary"}); null on the phone or when
/// there are none.
Future<String?> oldWebVotes() => device.oldWebVotes();

/// Kept in memory only: for the tests.
class MemoryStorage implements TextStorage {
  final texts = <String, String>{};

  @override
  Future<String?> read(String name) async => texts[name];

  @override
  Future<void> write(String name, String text) async => texts[name] = text;
}
