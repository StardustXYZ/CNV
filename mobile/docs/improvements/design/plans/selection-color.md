# Fix: Text selection and cursor use the default colors, not CNV's

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/selection-color
- **Needs new dependency**: none

## Why

`MaterialApp` picks the cursor and selection colors itself. CNV has its own violet accent (`CnvColors.accent`), so the search fields and the email/password fields should use it for cursor, handles and selection.

## Where

`grep -rn "textSelectionTheme" lib` finds nothing. The app has text fields (`TextField` in `in_sala_page.dart`, `in_uscita_page.dart`, `account_page.dart`).

```dart
// lib/theme.dart:29-33 — current
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: CnvColors.background,
    dividerColor: CnvColors.border,
```

## The fix

```dart
// target
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: CnvColors.background,
    dividerColor: CnvColors.border,
    textSelectionTheme: TextSelectionThemeData(
      selectionColor: CnvColors.accent.withValues(alpha: 0.3),
      selectionHandleColor: CnvColors.accent,
      cursorColor: CnvColors.accent,
    ),
```

## Steps

1. In `lib/theme.dart`, inside `cnvTheme()`'s `ThemeData(...)`, add the `textSelectionTheme:` argument right after `dividerColor:`.

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "textSelectionTheme" lib/theme.dart` → 1.
- By eye: tap "Cerca un titolo", type, long-press a word: cursor, handles and selection are violet.

## Don't touch

- The colors in `CnvColors`, the other parts of the theme. No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer the cursor and text selection are now the app's violet. Tap a search field and select some text to see it.
