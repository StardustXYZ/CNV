# Fix: Phone-style page transitions in the browser

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/web-page-transitions
- **Needs new dependency**: none

## Why

In the browser (and on desktop) a page that slides or zooms in looks like a phone app. The web should just open the page. The phone keeps its normal transitions.

## Where

`grep -rn "pageTransitionsTheme" lib` finds nothing; the app has a `web/` folder.

```dart
// lib/theme.dart:29-33 — current
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: CnvColors.background,
    dividerColor: CnvColors.border,
```

## The fix

The article uses Dart's dot shorthand (`.android`), which needs a newer Dart than this project's (`sdk: ^3.9.2`): write the full names (`TargetPlatform.android`).

Add to `lib/theme.dart` (add `import 'package:flutter/foundation.dart';` at the top):

```dart
/// No page transition in the browser or on desktop; the phone keeps its own.
const pageTransitions = PageTransitionsTheme(
  builders: {
    TargetPlatform.android: kIsWeb ? _NoTransitions() : ZoomPageTransitionsBuilder(),
    TargetPlatform.iOS: kIsWeb ? _NoTransitions() : CupertinoPageTransitionsBuilder(),
    TargetPlatform.macOS: _NoTransitions(),
    TargetPlatform.windows: _NoTransitions(),
    TargetPlatform.linux: _NoTransitions(),
    TargetPlatform.fuchsia: _NoTransitions(),
  },
);

class _NoTransitions extends PageTransitionsBuilder {
  const _NoTransitions();

  @override
  Duration get transitionDuration => Duration.zero;

  @override
  Duration get reverseTransitionDuration => Duration.zero;

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) => child;
}
```

and in `ThemeData(...)` after `dividerColor:` add `pageTransitionsTheme: pageTransitions,`.

## Steps

1. `lib/theme.dart`: add the import, the constant and the class (below `CnvColors`, above or below `cnvTheme`), and the `pageTransitionsTheme:` argument.

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "pageTransitionsTheme" lib/theme.dart` → 1.
- By eye: `flutter run -d chrome`, open a film: the page appears at once, with no slide. On the Android emulator the slide stays.

## Don't touch

- The routes, `Navigator.push` calls. No new dependencies.

## STOP if

- `flutter analyze` complains about the constant being non-const (`kIsWeb` is a const, so it should not): report instead of removing `const` blindly.
- A check fails twice.

## When you're done

Tell the developer the web version now opens pages instantly with no phone-style slide, while Android keeps its animation. Open a film in Chrome to see it.
