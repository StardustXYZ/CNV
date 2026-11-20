# Fix: Dates are built by hand instead of with the locale's formatter

> **Low value, the developer may prefer to skip this plan.** The app already writes dates in Italian with its own word lists (`format.dart`), and the result is identical to what `intl` would give. Doing it means adding `intl` and initializing the Italian locale in the app and in the tests. Only the fragments below are hand-built patterns.

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/format-date-times
- **Needs new dependency**: `intl` (declare it in `pubspec.yaml`; it is already installed as a dependency of `flutter_localizations`, so it adds nothing new to the app, but the project must list it to import it)

## Why

Dates shown to the user should come from `DateFormat` with the user's locale, not from `'${d.day}/${d.month}'` pieces.

## Where

```dart
// lib/data/format.dart:14-18 — current
String formatDay(String iso, String today) {
  if (iso == today) return 'oggi';
  if (iso == addDays(today, 1)) return 'domani';
  final d = parseDay(iso);
  return '${_weekdays[d.weekday - 1]} ${d.day}/${d.month}';
}
```

```dart
// lib/home.dart:~189 — current
        text = 'Dati aggiornati il ${when.day}/${when.month} alle ${_two(when.hour)}:${_two(when.minute)}';
```

(`longDate` and the calendar use the word lists `_months`/`_weekdays`; they are not hand-built numbers, leave them.)

## The fix

```dart
// target — lib/data/format.dart
import 'package:intl/intl.dart';
...
  return '${_weekdays[d.weekday - 1]} ${DateFormat('d/M').format(d)}';
```

```dart
// target — lib/home.dart (import 'package:intl/intl.dart';)
        text = 'Dati aggiornati il ${DateFormat('d/M').format(when)} alle ${DateFormat('HH:mm').format(when)}';
```

`DateFormat('d/M')` and `DateFormat('HH:mm')` need no locale data, so no `initializeDateFormatting` is required for these two patterns, and the output stays identical (`16/11`, `09:05`).

## Steps

1. `pubspec.yaml`: under `dependencies:` add `intl: ^0.20.2` (alphabetical, after `http`); then run `flutter pub get` and check that the version resolves (if `flutter_localizations` pins another `intl`, use the version `flutter pub get` suggests).
2. `lib/data/format.dart`: import and change the `formatDay` return.
3. `lib/home.dart`: import and change the `text =` line of `DataStatusBar`.

## Check it

- `flutter analyze` clean; `flutter test` passes unchanged (same output text).
- `grep -c "DateFormat" lib/data/format.dart` → 1; `lib/home.dart` → 2.

## Don't touch

- `longDate`, the calendar, `schedule.dart` (ISO dates for storage, not for the screen), the word lists.

## STOP if

- `flutter pub get` fails or changes other packages' versions.
- A test text changes. A check fails twice.

## When you're done

Tell the developer nothing looks different: dates are now produced by the standard formatter. Open "In uscita" and check the day names.
