# Fix: The last item of a list is covered by the system navigation bar

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/safe-area-replacement
- **Needs new dependency**: none

## Why

On phones with a bottom system bar (gesture bar or three buttons) the last item of a full-screen list slides under that bar and is hard to reach and read. Fixed paddings (24, 28, 16) do not follow the bar's real height, and `SafeArea` around a list is the wrong fix: it shrinks the list so items get cut off as they pass the bottom. The article's fix is a bottom padding as tall as the system bar (`MediaQuery.viewPaddingOf(context).bottom`), never smaller than a minimum.

## Where

The app is in `mobile/` (paths relative to it). Only lists that run to the bottom of the screen with nothing under them are affected: the pages pushed on top of the app (account, cinema, film, privacy) and the cinema menu (drawer). The five main pages (In sala, In uscita, Watchlist, Visti, Voti) sit above the bottom `NavigationBar`, which already keeps clear of the system bar: they are NOT part of this plan.

```dart
// lib/pages/account_page.dart:280-281 — current (page "Accedi con email")
          body: ListView(
            padding: const EdgeInsets.all(16),
```

```dart
// lib/pages/account_page.dart:403-404 — current (page "Ammessi")
          body: ListView(
            padding: const EdgeInsets.all(16),
```

```dart
// lib/pages/cinema_page.dart:77-78 — current (page of one cinema)
            child: ListView(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
```

```dart
// lib/pages/film_page.dart:36-37 — current (page of one film)
            child: ListView(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
```

```dart
// lib/pages/privacy_page.dart:56-57 — current
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
```

```dart
// lib/pages/cinema_page.dart:199-203 — current (the cinema menu: the wrong fix, SafeArea around a list)
    return Drawer(
      backgroundColor: CnvColors.surface,
      child: SafeArea(
        child: ListView(
          children: [
```

## The fix

New file `lib/widgets/bottom_padding.dart`, from the article:

```dart
import 'package:flutter/widgets.dart';

/// Breathing room at the end of a scrollable list: as tall as the system bar at the bottom
/// of the screen, and never less than [minimum]. Unlike SafeArea it does not shrink the list.
class BottomPadding extends StatelessWidget {
  const BottomPadding({super.key});

  static double of(BuildContext context, {double minimum = 16}) {
    final double viewPadding = MediaQuery.viewPaddingOf(context).bottom;
    return viewPadding > minimum ? viewPadding : minimum;
  }

  @override
  Widget build(BuildContext context) => SizedBox(height: of(context));
}
```

Then each list keeps its current padding, but its bottom value becomes dynamic. Keep each page's existing minimum (16, 24, 28):

```dart
// target — account_page.dart (both lists)
          body: ListView(
            padding: const EdgeInsets.all(16).copyWith(bottom: BottomPadding.of(context, minimum: 16)),
```

```dart
// target — cinema_page.dart:77 and film_page.dart:36
            child: ListView(
              padding: EdgeInsets.fromLTRB(12, 12, 12, BottomPadding.of(context, minimum: 24)),
```

```dart
// target — privacy_page.dart:56
      body: ListView(
        padding: EdgeInsets.fromLTRB(16, 12, 16, BottomPadding.of(context, minimum: 28)),
```

```dart
// target — cinema_page.dart, the drawer: keep the top safe, drop the bottom, pad the list instead
    return Drawer(
      backgroundColor: CnvColors.surface,
      child: SafeArea(
        bottom: false,
        child: ListView(
          padding: EdgeInsets.only(bottom: BottomPadding.of(context)),
          children: [
```

Match how the codebase already imports: relative imports like `import '../widgets/film_widgets.dart';`.

## Steps

1. Create `lib/widgets/bottom_padding.dart` with the code above.
2. `lib/pages/account_page.dart`: add `import '../widgets/bottom_padding.dart';` (after the `../theme.dart` import, keep alphabetical order with the other `../widgets/...` import) and change the two `padding:` lines at 281 and 404 to the target.
3. `lib/pages/cinema_page.dart`: add the same import; change line 78 to the target; in `CinemaDrawer.build` add `bottom: false,` to the `SafeArea` and `padding: EdgeInsets.only(bottom: BottomPadding.of(context)),` as the first argument of that `ListView`.
4. `lib/pages/film_page.dart`: add the import; change line 37.
5. `lib/pages/privacy_page.dart`: add the import; change line 57.
6. In every edited place the `context` used is the `build`/`builder` one already in scope; do not create new BuildContext variables. The horizontal `ListView` in `cinema_page.dart` (day chips) stays untouched.

## Check it

- `flutter analyze` exits clean.
- `flutter test` passes.
- `grep -c "BottomPadding.of" lib/pages/account_page.dart` → 2; `lib/pages/cinema_page.dart` → 2; `lib/pages/film_page.dart` → 1; `lib/pages/privacy_page.dart` → 1.
- `grep -c "bottom: false" lib/pages/cinema_page.dart` → 1.
- By eye in the emulator with three-button navigation (Pixel_2_API_33 uses the classic bar): open a film (tap a poster) and scroll to the end: the last block must stop with free space above the bar. Do the same in the Privacy page (Voti page → privacy link), in a cinema page (☰ menu → a cinema) and in the ☰ menu itself with a short screen.

## Don't touch

- The lists in the five main pages (`in_sala_page.dart`, `in_uscita_page.dart`, `watchlist_page.dart`, `visti_page.dart`, `voti_page.dart`) and `page_placeholder.dart`: the bottom `NavigationBar` already clears the system bar there.
- The `SafeArea` in `lib/widgets/vote_buttons.dart` (a small sheet, not a scrollable list) and the `SingleChildScrollView` in `lib/data/changelog.dart` (a dialog).
- No new dependencies, no refactors, renames or cleanups beyond the fix.

## STOP if

- The code at any location in "Where" doesn't match the quoted excerpt (the codebase moved on since this plan was written).
- The fix seems to require touching something in "Don't touch".
- A check fails twice.

## When you're done

Tell the developer that the film, cinema, privacy and account pages and the cinema menu now end with free space as tall as the phone's bottom bar, so the last line is never covered. To see it, open a film and scroll to the bottom.
