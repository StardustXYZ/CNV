# Fix: The day chips on a cinema page don't look scrollable

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/shader-mask
- **Needs new dependency**: none

## Why

The row of day chips ("Oggi", "domani", "lun 16/11"…) on a cinema page can end exactly at the screen edge, so nothing tells the user it scrolls. Fading the end edge hints that there is more.

## Where

`grep -rn "Axis.horizontal" lib` finds one horizontal list in the app.

```dart
// lib/pages/cinema_page.dart:~97-100 — current
                  SizedBox(
                    height: 40,
                    child: ListView(
                      scrollDirection: Axis.horizontal,
                      children: [
```

## The fix

Wrap the `ListView` in a `ShaderMask` that fades only the END edge (article: "fading only the bottom edge usually works best", horizontal = swap the gradient direction):

```dart
// target
                  SizedBox(
                    height: 40,
                    child: ShaderMask(
                      shaderCallback: (Rect bounds) => const LinearGradient(
                        begin: Alignment.centerLeft,
                        end: Alignment.centerRight,
                        colors: [Colors.white, Colors.white, Colors.white, Colors.transparent],
                        stops: [0.0, 0.0, 0.88, 1.0],
                      ).createShader(bounds),
                      blendMode: BlendMode.dstIn,
                      child: ListView(
                        scrollDirection: Axis.horizontal,
                        children: [
                          ...
                        ],
                      ),
                    ),
                  ),
```

Keep the `ListView`'s children exactly as they are.

## Steps

1. In `lib/pages/cinema_page.dart` wrap the horizontal `ListView` as shown (add one closing `)` and `,` after the `ListView`). Indent the inner lines by 2 more spaces.

## Check it

- `flutter analyze` clean; `flutter test` passes.
- `grep -c "ShaderMask" lib/pages/cinema_page.dart` → 1.
- By eye: open a cinema page; the last chip on the right fades out.

## Don't touch

- The chips themselves (`ChoiceChip`), the selection logic, any other list. No new dependencies.

## STOP if

- The code in "Where" doesn't match (the codebase moved on).
- A check fails twice.

## When you're done

Tell the developer the day chips now fade at the right edge, so it is clear they scroll. Open any cinema page (☰ menu → a cinema) to see it.
