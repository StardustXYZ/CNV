# Fix: Taps on tabs and votes happen in silence

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/haptic-feedback
- **Needs new dependency**: none (the article adds the `haptic_feedback` package for extra vibration types; two of Flutter's own `HapticFeedback` calls are enough for these two moments)

## Why

Nothing in the app vibrates. A very light vibration when the user changes tab or sets a vote makes the app feel responsive. (The emulator does not vibrate: this can only be felt on a real phone.)

## Where

`grep -rn "HapticFeedback" lib` finds nothing.

```dart
// lib/home.dart:~80-83 — current
  void _goTo(int index) {
    setState(() => _current = index);
    _pager.animateToPage(index, duration: const Duration(milliseconds: 250), curve: Curves.easeOutCubic);
  }
```

```dart
// lib/widgets/vote_buttons.dart:~36-41 — current
                    onTap: () async {
                      final nowSeen = v == 'S' && current != 'S';
                      await personal.toggleVote(film.id, v, today: today);
```

## The fix

Tab change: a selection click. Vote: a light impact.

```dart
// target — lib/home.dart
  void _goTo(int index) {
    HapticFeedback.selectionClick();
    setState(() => _current = index);
    ...
```

```dart
// target — lib/widgets/vote_buttons.dart
                    onTap: () async {
                      HapticFeedback.lightImpact();
                      final nowSeen = v == 'S' && current != 'S';
```

Both files need `import 'package:flutter/services.dart';` (at the top, before the relative imports, after `package:flutter/material.dart`).

## Steps

1. `lib/home.dart`: add the import and the `HapticFeedback.selectionClick();` first line of `_goTo`.
2. `lib/widgets/vote_buttons.dart`: add the import and `HapticFeedback.lightImpact();` first line of that `onTap`.

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "HapticFeedback" lib/home.dart` → 1; same for `lib/widgets/vote_buttons.dart` → 1.
- On a real phone: tapping a tab and tapping V/?/✓ gives a short vibration.

## Don't touch

- Anything else (no vibration on scrolling or refresh). No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer the tabs and the vote buttons now give a light vibration on a real phone (the emulator stays silent).
