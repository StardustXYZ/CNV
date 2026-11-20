# Fix: The app version is shown without the build number

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/show-app-version
- **Needs new dependency**: none (`package_info_plus` is already used; the app does not use Shorebird)

## Why

The Voti page (box "App") shows "Versione 1.1.0" but not the build number (`+16`). Builds with the same version but different build numbers are not distinguishable when a friend reports a problem. The article asks for version and build.

## Where

```dart
// lib/main.dart:~38-46 — current
      final version = (await PackageInfo.fromPlatform()).version;
      updates = UpdateStore(currentVersion: version);
      changelog = ChangelogStore(currentVersion: version);
```

```dart
// lib/data/updates.dart:~64-74 — current
  UpdateStore({
    required this.currentVersion,
    http.Client? client,
    TextStorage? storage,
  })  : _client = client ?? http.Client(),
        _storage = storage ?? deviceStorage();

  static const _name = 'aggiornamento.txt'; // the version dismissed with "Non ora"
  final String currentVersion;
```

```dart
// lib/pages/update_widgets.dart:~83-88 — current
        release != null
            ? 'Hai la versione ${store.currentVersion}: è uscita la ${release.version}.'
            : store.checkedAt != null
                ? 'Hai la versione ${store.currentVersion}, l’ultima uscita.'
                : 'Versione ${store.currentVersion}',
```

## The fix

`UpdateStore` gets an optional `build` and a label; versions are still compared without the build.

```dart
// target — lib/data/updates.dart
  UpdateStore({
    required this.currentVersion,
    this.build,
    http.Client? client,
    TextStorage? storage,
  })  : ...

  final String currentVersion;
  final String? build; // the build number (1.1.0+16 → "16"); null in the tests

  /// "1.1.0 (16)" for the screen.
  String get versionLabel => build == null || build!.isEmpty ? currentVersion : '$currentVersion ($build)';
```

```dart
// target — lib/main.dart
      final info = await PackageInfo.fromPlatform();
      updates = UpdateStore(currentVersion: info.version, build: info.buildNumber);
      changelog = ChangelogStore(currentVersion: info.version);
```

```dart
// target — lib/pages/update_widgets.dart
        release != null
            ? 'Hai la versione ${store.versionLabel}: è uscita la ${release.version}.'
            : store.checkedAt != null
                ? 'Hai la versione ${store.versionLabel}, l’ultima uscita.'
                : 'Versione ${store.versionLabel}',
```

## Steps

1. `lib/data/updates.dart`: add the optional `build` parameter/field and `versionLabel`.
2. `lib/main.dart`: read `PackageInfo` once and pass `build:`.
3. `lib/pages/update_widgets.dart`: use `store.versionLabel` in the three texts (only in those; `currentVersion` stays for comparisons).

## Check it

- `flutter analyze` clean; `flutter test` passes (the tests build `UpdateStore` without `build`, so their texts do not change, e.g. `Hai la versione 0.11.0: è uscita la 0.12.0.`).
- `grep -c "versionLabel" lib/pages/update_widgets.dart` → 3.
- By eye (hot restart): Voti page → box "App": "Versione 1.1.0 (16)".

## Don't touch

- `compareVersions`, the update check, `ChangelogStore`. No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer the "App" box on the Voti page now shows the version with its build number, e.g. "1.1.0 (16)". Open the Voti page and scroll to the bottom.
