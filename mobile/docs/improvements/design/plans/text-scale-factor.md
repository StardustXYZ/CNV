# Fix: Large system text sizes break the layouts

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/text-scale-factor
- **Needs new dependency**: none

## Why

Users who raise the text size in Android settings can make rows overflow. The app should respect the choice but cap it at x1.1.

## Where

`grep -rn "textScaler" lib` only finds one read-only use in `film_page.dart`; nothing limits it app-wide.

```dart
// lib/main.dart, in MaterialApp(...) — current
              builder: (context, child) => ColoredBox(
                color: Colors.black,
                child: Center(
                  child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: phoneWidth), child: child),
                ),
              ),
```

## The fix

Wrap the result in a `MediaQuery` with the clamped scaler (keep the existing `ColoredBox`/`Center` code inside):

```dart
// target
              builder: (context, child) {
                final media = MediaQuery.of(context);
                return MediaQuery(
                  data: media.copyWith(textScaler: media.textScaler.clamp(maxScaleFactor: 1.1)),
                  child: ColoredBox(
                    color: Colors.black,
                    child: Center(
                      child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: phoneWidth), child: child),
                    ),
                  ),
                );
              },
```

## Steps

1. `lib/main.dart`: replace the `builder:` of `MaterialApp` as shown (keep the comment above it).

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "maxScaleFactor" lib/main.dart` → 1.
- By eye: in the emulator open Settings → Display → Font size → largest, then open CNV: text is slightly bigger than normal at most and nothing overflows (no yellow-black stripes) in "In sala", a film page and the Voti page.

## Don't touch

- The `textScaler` read in `film_page.dart:~243` (it keeps working). No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.
- With the largest font something still overflows: report where (a separate fix is needed).

## When you're done

Tell the developer the text size follows the phone's setting only up to a small increase, so layouts stay intact. Set the phone's font to "largest" and open the app.
