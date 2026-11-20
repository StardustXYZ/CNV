# Fix: The browser tab always says "CNV – Chi Ni Vidimu"

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/browser-tab-title
- **Needs new dependency**: none

## Why

On the web version every page has the same tab title, so with several tabs open (or in history) they look alike. The tab should say which page it is. (Only the browser is affected; on the phone `Title` does nothing visible.)

## Where

`web/` exists; `grep -rn "Title(" lib` finds only `CnvTitle` (the logo) and no `Title` widget. The app uses plain `Navigator` (no router), with these screens: `HomeShell` (5 tabs), `CinemaPage`, `FilmPage`, `PrivacyPage`, the two account pages in `account_page.dart`.

```dart
// lib/pages/film_page.dart:~32-33 — current
        return Scaffold(
          appBar: AppBar(title: Text(current.title, overflow: TextOverflow.ellipsis)),
```

## The fix

The article's first option: a `Title` widget around each page (the router-based wrapper is not available without a router).

```dart
// target — pattern, e.g. film_page.dart
        return Title(
          title: '${current.title} · CNV',
          color: CnvColors.background,
          child: Scaffold(
            ...
          ),
        );
```

Titles:
- `HomeShell` (`lib/home.dart`, wrap the `Scaffold` returned in `build`): `'${cnvPages[_current].label} · CNV'`.
- `CinemaPage` (`lib/pages/cinema_page.dart`, around its `Scaffold`): `'${cinema?.name ?? widget.slug} · CNV'`.
- `FilmPage`: `'${current.title} · CNV'`.
- `PrivacyPage`: `'Privacy · CNV'`.
- Account email page: `'Accedi · CNV'`; "Ammessi" page: `'Ammessi · CNV'`.

`color` must be opaque (`CnvColors.background` is `0xFF121212`: fine). Each file already imports `theme.dart`; `home.dart` does too.

## Steps

1. Wrap the `Scaffold` of each of the six screens above in `Title(...)`; remember the extra closing parenthesis and re-indent the `Scaffold`.

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "Title(" lib/pages/film_page.dart` → 1 (similarly 1 each in `cinema_page.dart`, `privacy_page.dart`, `home.dart` (besides `CnvTitle`), 2 in `account_page.dart`).
- By eye (browser): `flutter run -d chrome`, move between tabs and open a film: the tab title follows.

## Don't touch

- `CnvTitle` (the logo text), the `<title>` in `index.html` (it stays as the first title). No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.

## Known limit (tell the developer)

After closing a pushed page (back), the title returns to the previous page's only when that page rebuilds, not immediately. A full fix needs a navigator observer; do not add it here.

## When you're done

Tell the developer the browser tab now names the page (Film, Cinema, tab names). Open the web version and move around.
