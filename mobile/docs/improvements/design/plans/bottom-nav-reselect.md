# Fix: Tapping the open tab again does nothing

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/bottom-nav-reselect
- **Needs new dependency**: none

## Why

On the bottom menu, tapping the tab you are already on should scroll that page back to the top: it is what users of other apps expect. Today `_goTo` just re-selects the same page.

## Where

```dart
// lib/home.dart:~80-83 — current
  void _goTo(int index) {
    setState(() => _current = index);
    _pager.animateToPage(index, duration: const Duration(milliseconds: 250), curve: Curves.easeOutCubic);
  }
```

```dart
// lib/home.dart:~122-132 — current
                        children: [
                          if (ready) InSalaPage(store: _store) else PagePlaceholder(page: cnvPages[0]),
                          if (ready) InUscitaPage(store: _store) else PagePlaceholder(page: cnvPages[1]),
                          if (ready) WatchlistPage(store: _store) else PagePlaceholder(page: cnvPages[2]),
                          if (ready) VistiPage(store: _store) else PagePlaceholder(page: cnvPages[3]),
                          VotiPage(store: _store),
                        ],
...
          bottomNavigationBar: NavigationBar(
            selectedIndex: _current,
            onDestinationSelected: _goTo,
```

Each of the five pages has one vertical `ListView(` (the first, page-level one) and a constructor `const XxxPage({super.key, required this.store});`:
`lib/pages/in_sala_page.dart` (`InSalaPage`, ListView ~104), `in_uscita_page.dart` (`InUscitaPage`, ~70), `watchlist_page.dart` (`WatchlistPage`, ~33), `visti_page.dart` (`VistiPage`, ~32), `voti_page.dart` (`VotiPage`, ~29).

## The fix

`HomeShell` keeps one `ScrollController` per page and hands it to the page; a tap on the already-open tab scrolls it to the top.

```dart
// target — lib/home.dart, in _HomeShellState
  final _scrollers = List.generate(cnvPages.length, (_) => ScrollController());

  @override
  void dispose() {
    _pager.dispose();
    for (final s in _scrollers) {
      s.dispose();
    }
    super.dispose();
  }

  void _onTab(int index) {
    if (index != _current) return _goTo(index);
    final scroller = _scrollers[index];
    if (scroller.hasClients && scroller.offset > 0) {
      scroller.animateTo(0, duration: const Duration(milliseconds: 300), curve: Curves.easeOutCubic);
    }
  }
```

```dart
// target — lib/home.dart, the pages and the bar
                          if (ready) InSalaPage(store: _store, scroll: _scrollers[0]) else PagePlaceholder(page: cnvPages[0]),
                          if (ready) InUscitaPage(store: _store, scroll: _scrollers[1]) else PagePlaceholder(page: cnvPages[1]),
                          if (ready) WatchlistPage(store: _store, scroll: _scrollers[2]) else PagePlaceholder(page: cnvPages[2]),
                          if (ready) VistiPage(store: _store, scroll: _scrollers[3]) else PagePlaceholder(page: cnvPages[3]),
                          VotiPage(store: _store, scroll: _scrollers[4]),
...
            onDestinationSelected: _onTab,
```

In each of the five pages: add a field and constructor parameter, and give it to the page-level `ListView`:

```dart
  const InSalaPage({super.key, required this.store, this.scroll});
  final ScrollController? scroll;
  ...
      child: ListView(
        controller: widget.scroll,   // in a State class use widget.scroll; in a StatelessWidget use scroll
```

(`InSalaPage` and `InUscitaPage` are `StatefulWidget`s: the ListView is in the State class, so `widget.scroll`. The other three are `StatelessWidget`s: `scroll`.)

## Steps

1. `lib/home.dart`: add `_scrollers`, extend `dispose`, add `_onTab`, pass `scroll:` to the five pages, set `onDestinationSelected: _onTab`.
2. The five page files: add the optional `scroll` field/parameter and `controller:` on the page-level `ListView`. Do not touch other ListViews in those files.
3. `PagePlaceholder` stays as is (it has no scroll controller).

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "_scrollers" lib/home.dart` → at least 6; `grep -c "controller: " lib/pages/voti_page.dart` → 1 (and one in each of the other four files).
- By eye (hot restart, not hot reload: new state): scroll "In sala" down, tap "In sala" in the bottom menu again: the list scrolls smoothly to the top. Tapping another tab still switches page.

## Don't touch

- The swipe between pages, `_goTo`, the placeholders. No new dependencies.

## STOP if

- A page file has more than one page-level vertical `ListView` and it is unclear which to use — report instead of guessing.
- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer that tapping the tab you are already on now scrolls that page back to the top. Scroll down in "In sala" and tap its icon again.
