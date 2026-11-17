import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web/web.dart' as web;

import 'storage.dart';

TextStorage deviceStorage() => BrowserStorage();

/// The keys of the old web version (phone/app.js), each a JSON map by film code.
const _oldKeys = {'votes': 'cnv.votes', 'seen': 'cnv.seen', 'exported': 'cnv.exported', 'diary': 'cnv.diary'};

Future<String?> oldWebVotes() async {
  try {
    final storage = web.window.localStorage;
    if (storage.getItem(_oldKeys['votes']!) == null) return null;
    final copy = <String, Object?>{};
    for (final e in _oldKeys.entries) {
      final text = storage.getItem(e.value);
      copy[e.key] = text == null ? <String, Object?>{} : jsonDecode(text);
    }
    return jsonEncode(copy);
  } catch (err) {
    debugPrint('Voti della vecchia versione web non leggibili: $err');
    return null;
  }
}

/// The browser's storage for this site (it stays when the page is closed).
class BrowserStorage implements TextStorage {
  static const _prefix = 'cnv-app.';

  @override
  Future<String?> read(String name) async {
    try {
      return web.window.localStorage.getItem('$_prefix$name');
    } catch (err) {
      debugPrint('$name non leggibile: $err');
      return null;
    }
  }

  @override
  Future<void> write(String name, String text) async => web.window.localStorage.setItem('$_prefix$name', text);
}
