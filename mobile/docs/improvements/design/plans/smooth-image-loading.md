# Fix: Posters pop in without a transition in the browser

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/smooth-image-loading
- **Needs new dependency**: none (the article uses `image_fade`; this app already has the same behavior on the phone through `CachedNetworkImage`, which fades in by default, and a grey placeholder with 🎬 and an error state. Only the browser path is missing the fade, and it is fixed with Flutter's built-in `AnimatedSwitcher`)

## Why

On the phone the poster already has a placeholder, a fade-in and a quiet failure state. In the browser (`kIsWeb`) the code uses plain `Image.network`, which swaps placeholder for image with no transition. The fix is a short cross-fade.

## Where

```dart
// lib/widgets/film_widgets.dart:~45-52 — current
                ? Image.network(
                    url!,
                    fit: BoxFit.cover,
                    webHtmlElementStrategy: WebHtmlElementStrategy.prefer,
                    loadingBuilder: (_, image, progress) => progress == null ? image : placeholder,
                    errorBuilder: (_, _, _) => placeholder,
                  )
```

## The fix

```dart
// target
                ? Image.network(
                    url!,
                    fit: BoxFit.cover,
                    webHtmlElementStrategy: WebHtmlElementStrategy.prefer,
                    loadingBuilder: (_, image, progress) => AnimatedSwitcher(
                      duration: const Duration(milliseconds: 200),
                      child: KeyedSubtree(
                        key: ValueKey(progress == null),
                        child: progress == null ? image : placeholder,
                      ),
                    ),
                    errorBuilder: (_, _, _) => placeholder,
                  )
```

Do NOT change the `CachedNetworkImage` branch (phone).

## Steps

1. In `lib/widgets/film_widgets.dart` replace the `loadingBuilder:` line as shown.

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "AnimatedSwitcher" lib/widgets/film_widgets.dart` → 1.
- By eye (browser only): `flutter run -d chrome`, open "In sala": posters fade in. On the Android emulator nothing changes (it already fades).

## Don't touch

- The phone branch (`CachedNetworkImage`), the placeholder design, `Poster`'s size/AspectRatio. No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.
- In Chrome the posters stop showing at all (the AnimatedSwitcher and the HTML image strategy clash): revert and report.

## When you're done

Tell the developer that in the browser the posters now fade in; on the phone they already did. Open the web version to see it.
