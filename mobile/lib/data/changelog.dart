import 'package:flutter/material.dart';

import 'storage.dart';
import 'updates.dart' show compareVersions;

/// What changed in a version, in a few short lines (newest version first).
@immutable
class ChangelogEntry {
  const ChangelogEntry(this.version, this.changes);

  final String version; // "1.2.0", as in pubspec.yaml (without the +build)
  final List<String> changes;
}

/// The novelties of each version. Add a new entry at the TOP for every release.
const changelog = [
  ChangelogEntry('1.1.1', [
    'ESEMPIO: sostituisci questa riga con le novità vere di questa versione.',
  ]),
];

/// Remembers the last version the user has seen and tells what is new since then.
class ChangelogStore {
  ChangelogStore({required this.currentVersion, TextStorage? storage, this.entries = changelog})
      : _storage = storage ?? deviceStorage();

  static const _name = 'novita.txt'; // the last version whose novelties were shown
  final String currentVersion;
  final List<ChangelogEntry> entries;
  final TextStorage _storage;

  /// The novelties of every version after the last one seen, up to this one. Empty on a
  /// first install and when nothing changed; in both cases this version counts as seen.
  Future<List<String>> unseen() async {
    try {
      final lastSeen = (await _storage.read(_name))?.trim() ?? '';
      if (lastSeen.isEmpty || compareVersions(lastSeen, currentVersion) >= 0) {
        if (lastSeen.isEmpty) await markSeen(); // first install: nothing to catch up on
        return [];
      }
      final changes = [
        for (final e in entries)
          if (compareVersions(e.version, lastSeen) > 0 && compareVersions(e.version, currentVersion) <= 0)
            ...e.changes,
      ];
      if (changes.isEmpty) await markSeen();
      return changes;
    } catch (err) {
      debugPrint('Novità non lette: $err');
      return [];
    }
  }

  /// This version's novelties were shown: do not show them again.
  Future<void> markSeen() async {
    try {
      await _storage.write(_name, currentVersion);
    } catch (err) {
      debugPrint('Novità non salvate: $err');
    }
  }
}

/// The dialog with the novelties (the same wording as the app: Italian, short).
Future<void> showChangelog(BuildContext context, List<String> changes) => showDialog<void>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Novità'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final c in changes)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [const Text('•  '), Expanded(child: Text(c))],
                  ),
                ),
            ],
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.of(dialog).pop(), child: const Text('Ok'))],
      ),
    );
