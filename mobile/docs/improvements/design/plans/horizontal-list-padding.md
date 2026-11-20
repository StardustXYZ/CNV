# Fix: The day chips are clipped at the page's padding instead of the screen edge

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/horizontal-list-padding
- **Needs new dependency**: none

## Why

The cinema page is a `ListView` with 12px of horizontal padding, so the sideways list of day chips inside it is cut 12px from the screen edge, instead of sliding off the screen. The article's rule: horizontal lists should reach the edges and carry their own padding.

## Where

Only one horizontal list in the app.

```dart
// lib/pages/cinema_page.dart:~77-78 — current (page ListView; it already uses BottomPadding)
            child: ListView(
              padding: EdgeInsets.fromLTRB(12, 12, 12, BottomPadding.of(context, minimum: 24)),
```

```dart
// lib/pages/cinema_page.dart:~97-100 — current (the chips)
                  SizedBox(
                    height: 40,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
```

## The fix

The article removes the page padding and pads each child. Here every other child (films, notices, titles) relies on the 12px, so instead the chip list is widened by 12px on each side (it leaves the page padding) and gets its own 12px padding:

```dart
// target
                  SizedBox(
                    height: 40,
                    child: LayoutBuilder(
                      builder: (context, box) => OverflowBox(
                        minWidth: box.maxWidth + 24,
                        maxWidth: box.maxWidth + 24,
                        child: ListView(
                          scrollDirection: Axis.horizontal,
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          children: [
                            ...
                          ],
                        ),
                      ),
                    ),
                  ),
```

## Steps

1. `lib/pages/cinema_page.dart`: wrap the horizontal `ListView` as shown and add its `padding:`. Keep its children unchanged. (If the plan `shader-mask` was applied before, its `ShaderMask` wraps the `ListView` inside the `OverflowBox`: keep that nesting `OverflowBox → ShaderMask → ListView`. If `tab-visibility` was applied, keep its keys.)

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "OverflowBox" lib/pages/cinema_page.dart` → 1.
- By eye: open a cinema page with several days: the chips start aligned with the films below (12px in) and, when scrolled, slide to the screen edge instead of being cut 12px before it.

## Don't touch

- The page `ListView`'s own padding, the films list, other pages. No new dependencies.

## STOP if

- The chips lose their tap or the list jumps: revert and report.
- The code in "Where" doesn't match, or a check fails twice.

## When you're done

Tell the developer the day chips now slide all the way to the screen edge. Open a cinema page and swipe the chips sideways.
