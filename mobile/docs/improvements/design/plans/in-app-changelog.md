# Fix: After an update, nothing tells users what's new

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/in-app-changelog
- **Needs new dependency**: none (the app already has `package_info_plus`, its own `TextStorage` for small saved texts, and `compareVersions()` for versions; the article's `pub_semver` and `shared_preferences` are NOT needed)

## Why

After an update the app opens exactly as before, so nobody learns about the fixes and features. The article's fix: keep a versioned changelog in Dart, remember the last version the user has seen, and on the first open of a newer version show everything they missed (also the versions in between if they skipped some). On a first install show nothing.

## Where

The app is in `mobile/` (paths below are relative to it). Nothing in the app shows what changed: `grep -rniE "changelog|whats_new|release_notes|last_seen_version" lib` finds nothing. These are the spots the fix connects to, quoted from the current code.

```dart
// lib/main.dart:36-45 — current: the phone reads its version here (the browser is skipped)
  final account = AccountStore(backend);
  UpdateStore? updates;
  // In the browser the page is always the latest version, and notifications arrive on the phone
  if (!kIsWeb) {
    try {
      updates = UpdateStore(currentVersion: (await PackageInfo.fromPlatform()).version);
    } catch (err) {
      debugPrint('Versione non letta: $err');
    }
  }
```

```dart
// lib/main.dart:46-54 — current: runApp
  runApp(
    CnvApp(
      updates: updates,
      account: account,
      notifications: !kIsWeb && backend != null && push != null ? NotificationStore(account, backend, push) : null,
      foreground: kIsWeb ? null : push?.foreground(),
    ),
  );
```

```dart
// lib/main.dart:58-82 — current: CnvApp fields
class CnvApp extends StatefulWidget {
  const CnvApp({
    super.key,
    this.store,
    this.personal,
    this.account,
    this.notifications,
    this.foreground,
    this.updates,
  });
  ...
  final UpdateStore? updates; // newer versions on GitHub (none in the tests)
```

```dart
// lib/main.dart, inside MaterialApp — current
              home: HomeShell(store: _store),
```

```dart
// lib/home.dart:59-80 — current
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.store});

  final DataStore store;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  final _pager = PageController();
  late final DataStore _store = widget.store;
  int _current = 0;

  @override
  void dispose() {
    _pager.dispose();
    super.dispose();
  }
```

```dart
// lib/data/updates.dart:25-34 — existing helper to reuse, do not change
int compareVersions(String a, String b) { ... }
```

```dart
// lib/data/storage.dart — existing helpers to reuse, do not change
abstract class TextStorage { Future<String?> read(String name); Future<void> write(String name, String text); }
TextStorage deviceStorage() => device.deviceStorage();
class MemoryStorage implements TextStorage { ... } // for the tests
```

## The fix

Imitate `lib/data/updates.dart` (`UpdateStore`): a small class that reads/writes one text file through `TextStorage`.

New file `lib/data/changelog.dart`:

```dart
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
```

`lib/main.dart`: create the store next to `updates` (phone only, like the update check), pass it down, hand it to `HomeShell`:

```dart
// target — lib/main.dart, in main()
  UpdateStore? updates;
  ChangelogStore? changelog;
  if (!kIsWeb) {
    try {
      final version = (await PackageInfo.fromPlatform()).version;
      updates = UpdateStore(currentVersion: version);
      changelog = ChangelogStore(currentVersion: version);
    } catch (err) {
      debugPrint('Versione non letta: $err');
    }
  }
  runApp(
    CnvApp(
      updates: updates,
      changelog: changelog,
      ...
```

```dart
// target — lib/main.dart, CnvApp
    this.updates,
    this.changelog,
  ...
  final ChangelogStore? changelog; // the novelties of the version just installed (none in the tests)
  ...
              home: HomeShell(store: _store, changelog: widget.changelog),
```

```dart
// target — lib/home.dart
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.store, this.changelog});

  final DataStore store;
  final ChangelogStore? changelog;
  ...
  @override
  void initState() {
    super.initState();
    // On the first open after an update: what is new, once
    widget.changelog?.unseen().then((changes) async {
      if (changes.isEmpty || !mounted) return;
      await widget.changelog!.markSeen();
      if (mounted) await showChangelog(context, changes);
    });
  }
```

## Steps

1. Create `lib/data/changelog.dart` with the code above (imports: `package:flutter/material.dart`, `storage.dart`, `updates.dart show compareVersions`). Do not add a new package.
2. In `lib/main.dart` add `import 'data/changelog.dart';` (keep the imports alphabetical, after `account.dart`), then make the three edits shown (creation in `main()`, the `changelog` field/constructor parameter on `CnvApp`, the `HomeShell(...)` call).
3. In `lib/home.dart` add `import 'data/changelog.dart';`, the `changelog` field and constructor parameter on `HomeShell`, and the `initState` shown above (add it above `dispose`, in `_HomeShellState`).
4. Add `test/changelog_test.dart` (the project's tests use `MemoryStorage`, see `test/updates_test.dart`) covering: first install → `unseen()` returns `[]` and the file now holds the version; last seen `1.0.0`, current `1.2.0`, entries for 1.1.0 and 1.2.0 → both lists of changes, in order; last seen equal to current → `[]`; an entry newer than current is not shown.
5. Do NOT edit `pubspec.yaml` and do NOT bump the version in this plan.

## Check it

- `flutter analyze` exits clean.
- `flutter test` passes (all existing tests too: they do not pass `changelog`, so nothing shows).
- `grep -c "ChangelogStore" lib/main.dart` → at least 2; `grep -c "showChangelog" lib/home.dart` → 1.
- By eye, in the emulator (the developer does this, one time):
  1. Run the app once (`F5`). Nothing appears (it counts as a first install and saves `1.1.0`).
  2. Stop it. In `pubspec.yaml` set `version: 1.1.1+17` (temporary, for the test), and `F5` again as a full restart. The "Novità" dialog with the example line appears; tap "Ok".
  3. Restart again: it does not appear a second time.
  4. Put `pubspec.yaml` back to `1.1.0+16` unless the developer wants to keep the new version.

## Don't touch

- `lib/data/updates.dart`, `lib/pages/update_widgets.dart`: the "new APK on GitHub" notice is a different feature, keep it as is.
- The browser version: it is skipped on purpose (the page is always the latest version, same as the update check).
- No new dependencies, no rename or cleanup of existing code.

## STOP if

- The code at any location in "Where" doesn't match the quoted excerpt (the codebase moved on since this plan was written).
- The fix seems to require touching something in "Don't touch".
- A check fails twice.
- You would have to invent the real novelties: the line in `changelog` is an example. Ask the developer for the real text of each version.

## When you're done

Tell the developer that after an update the app now shows a "Novità" box once, with the list of changes since the last version they opened, and that nothing is shown on a fresh install. To see it, follow the three-step emulator check above. Remind them that from now on every release needs a new entry at the top of `changelog` in `lib/data/changelog.dart`.
