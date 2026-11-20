# Fix: A half-visible day chip stays half-visible when tapped

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/tab-visibility
- **Needs new dependency**: none

## Why

On a cinema page the day chips scroll sideways. Tapping a chip that is cut by the edge selects it but leaves it cut. The tapped chip should scroll fully into view.

## Where

It is the only custom horizontal selector (`TabBar` is not used anywhere).

```dart
// lib/pages/cinema_page.dart:~97-111 — current
                  SizedBox(
                    height: 40,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      children: [
                        for (final d in days)
                          Padding(
                            padding: const EdgeInsets.only(right: 6),
                            child: ChoiceChip(
                              label: Text(d == programme.day ? 'Oggi' : capitalize(formatDay(d, programme.day))),
                              selected: d == selected,
                              showCheckmark: false,
                              onSelected: (_) => setState(() => _chosen = d),
                            ),
                          ),
```

(`_chosen` is a `String?` in the page's State class.)

## The fix

One `GlobalKey` per day, and `Scrollable.ensureVisible` when a chip is chosen.

```dart
// target — in the State class of the cinema page
  final _dayKeys = <String, GlobalKey>{};

  void _showDay(String day) {
    setState(() => _chosen = day);
    final context = _dayKeys[day]?.currentContext;
    if (context == null) return;
    Scrollable.ensureVisible(
      context,
      alignment: 0.5,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
    );
  }
```

```dart
// target — the chip
                          Padding(
                            key: _dayKeys.putIfAbsent(d, GlobalKey.new),
                            padding: const EdgeInsets.only(right: 6),
                            child: ChoiceChip(
                              ...
                              onSelected: (_) => _showDay(d),
                            ),
                          ),
```

## Steps

1. `lib/pages/cinema_page.dart`: add `_dayKeys` and `_showDay` to the State class that owns `_chosen`.
2. Give each chip's `Padding` the key and change `onSelected` to call `_showDay(d)`.

## Check it

- `flutter analyze` clean; `flutter test` passes (the cinema tests tap chips).
- `grep -c "ensureVisible" lib/pages/cinema_page.dart` → 1.
- By eye: on a cinema with many days, tap a chip at the edge: it slides to the centre.

## Don't touch

- The day selection logic (`_chosen`, `selected`), other pages. No new dependencies.

## STOP if

- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer that tapping a partly hidden day chip now scrolls it into view. Open a cinema page and tap the last chip.
