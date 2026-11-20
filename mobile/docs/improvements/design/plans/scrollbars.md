# Fix: Vertical lists have no scrollbar

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/scrollbars
- **Needs new dependency**: none

## Why

A scrollbar shows where you are in a long list and how much is left. On the phone Flutter adds none. On desktop browsers it adds one automatically, so the app-wide fix must apply only on the phone, otherwise the two clash.

## Where

`grep -rn "scrollBehavior\|Scrollbar" lib` finds nothing.

```dart
// lib/main.dart, in MaterialApp(...) — current
              title: 'CNV',
              debugShowCheckedModeBanner: false,
              scaffoldMessengerKey: _messenger,
              theme: cnvTheme(),
```

## The fix

The article's app-wide variant (`AlwaysScrollbarBehavior`), limited to phones and to vertical lists (the horizontal day chips and the page swiper stay free of scrollbars):

```dart
// target — lib/theme.dart (add import 'package:flutter/foundation.dart'; if not there yet)
/// A scrollbar on vertical lists on the phone; on desktop browsers Flutter already adds its own.
class CnvScrollBehavior extends MaterialScrollBehavior {
  const CnvScrollBehavior();

  @override
  Widget buildScrollbar(BuildContext context, Widget child, ScrollableDetails details) {
    final isPhone = defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS;
    final vertical = details.direction == AxisDirection.down || details.direction == AxisDirection.up;
    if (!isPhone || !vertical) return super.buildScrollbar(context, child, details);
    return Scrollbar(controller: details.controller, child: child);
  }
}
```

```dart
// target — lib/main.dart, MaterialApp
              scrollBehavior: const CnvScrollBehavior(),
```

## Steps

1. `lib/theme.dart`: add the class (and the `foundation` import if missing).
2. `lib/main.dart`: add `scrollBehavior: const CnvScrollBehavior(),` after `theme: cnvTheme(),` (the file already imports `theme.dart`).

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "CnvScrollBehavior" lib/main.dart` → 1; `lib/theme.dart` → 2.
- By eye: scroll "In sala": a thin scrollbar appears at the right edge. The day chips and the page swipe show none. In Chrome on a PC there is a single scrollbar.

## Don't touch

- The lists themselves, controllers. No new dependencies.

## STOP if

- `buildScrollbar`'s signature differs in this Flutter version (`flutter analyze` error): report the exact error.
- A check fails twice.

## When you're done

Tell the developer vertical lists now show a thin scrollbar on the phone. Scroll "In sala" to see it.
