# Fix: The "Dove hai visto…?" sheet opens and closes mechanically

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/smooth-draggable-bottom-sheets
- **Needs new dependency**: none

## Why

`showModalBottomSheet` moves with a stiff, mechanical animation. The article's `showSpringBottomSheet` is a drop-in with spring motion and a drag that keeps the speed of the swipe. The app has exactly one such small non-scrolling sheet.

## Where

`grep -rn "showModalBottomSheet" lib` finds one use (the only sheet; the other pop-ups are `showDialog`).

```dart
// lib/widgets/vote_buttons.dart:~101-106 — current
  final choice = await showModalBottomSheet<String>(
    context: context,
    backgroundColor: CnvColors.surface,
    builder: (sheet) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
```

## The fix

1. Create `lib/widgets/spring_sheet.dart` with the article's file below, with these adaptations:
   - `SheetContainer`'s `ColoredBox(color: Colors.white, ...)` → `color: CnvColors.surface` and `import '../theme.dart';` (the sheet keeps the app's dark surface, as the current `backgroundColor`).
   - Dart dot shorthand (`type: .transparency`, `const .vertical(...)`) is not supported by this project's SDK (`^3.9.2`): write `MaterialType.transparency` and `const BorderRadius.vertical(`. `flutter analyze` reports any other.
2. In `lib/widgets/vote_buttons.dart` (add `import 'spring_sheet.dart';`):

```dart
// target
  final choice = await showSpringBottomSheet<String>(
    context: context,
    builder: (sheet) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        ... // the same children as now
```

(the `backgroundColor:` argument is removed: `SheetContainer` provides the surface). Keep the `SafeArea`, the `Column` and the `ListTile`s, whose `Navigator.of(sheet).pop(...)` calls still work.

### The article's file (verbatim)

```dart
import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
  
/// Shows a modal sheet anchored to the bottom edge of the screen.
///
/// A spring-driven replacement for showModalBottomSheet. The sheet enters
/// and exits on smooth springs, and dragging it drives the route animation
/// directly, so the velocity of a released fling is carried into the open
/// or close spring.
///
/// The sheet surface comes from [SheetContainer]; the widget returned by
/// [builder] brings only its content and padding.
///
/// Returns a [Future] that resolves to the value passed to [Navigator.pop]
/// when the sheet is closed.
Future<T?> showSpringBottomSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
}) {
  return Navigator.of(context).push(
    SpringSheetRoute<T>(
      builder: builder,
    ),
  );
}
  
/// A route that shows a spring-driven modal sheet at the bottom of the
/// screen.
class SpringSheetRoute<T> extends PopupRoute<T> {
  SpringSheetRoute({
    required this.builder,
    super.settings,
  });
  
  /// Builds the content of the sheet.
  final WidgetBuilder builder;
  
  // SwiftUI's .smooth spring written out as plain numbers: critically
  // damped, stiffness 4pi^2 / duration^2, at 300ms in and 200ms out.
  static const SpringDescription _enterSpring = SpringDescription(
    mass: 1,
    stiffness: 438.6,
    damping: 41.9,
  );
  static const SpringDescription _exitSpring = SpringDescription(
    mass: 1,
    stiffness: 987.0,
    damping: 62.8,
  );
  
  // Resistance applied when dragging past fully open.
  static const double _overdragResistance = 100;
  
  // Thresholds past which a released drag closes the sheet: fling speed in
  // sheet heights per second, or resting position as a fraction of height.
  static const double _closeVelocity = 0.9;
  static const double _closePosition = 0.5;
  
  // Release velocity in sheet heights per second (positive is downward),
  // carried from the drag into the close simulation.
  double? _releaseVelocity;
  
  bool _popped = false;
  
  @override
  Color? get barrierColor => const Color(0x8A000000);
  
  @override
  bool get barrierDismissible => true;
  
  @override
  String? get barrierLabel => null;
  
  @override
  Duration get transitionDuration => const Duration(milliseconds: 300);
  
  @override
  Duration get reverseTransitionDuration => const Duration(milliseconds: 200);
  
  // The scrim fades with the clamped animation so that dragging past fully
  // open does not push the barrier curve out of range. The slide reads the
  // raw controller.
  @override
  Animation<double>? get animation {
    final Animation<double>? raw = super.animation;
    if (raw == null) return null;
  
    return _ClampedAnimation(raw);
  }
  
  @override
  AnimationController createAnimationController() {
    return AnimationController.unbounded(
      duration: transitionDuration,
      reverseDuration: reverseTransitionDuration,
      vsync: navigator!,
    );
  }
  
  @override
  Simulation? createSimulation({required bool forward}) {
    final double velocity = _releaseVelocity ?? 0;
    _releaseVelocity = null;
  
    return SpringSimulation(
      forward ? _enterSpring : _exitSpring,
      controller?.value ?? 0,
      forward ? 1 : 0,
      -velocity,
      snapToEnd: true,
    );
  }
  
  @override
  bool didPop(T? result) {
    _popped = true;
  
    return super.didPop(result);
  }
  
  void _dragBy(double relativeDelta) {
    if (_popped) return;
  
    final AnimationController controller = this.controller!;
  
    double delta = relativeDelta;
    if (controller.value > 1) {
      final double overshoot = controller.value - 1;
      delta *= 1 / (1 + overshoot * _overdragResistance);
    }
    controller.value -= delta;
  }
  
  void _endDrag(double relativeVelocity) {
    if (_popped) return;
    final AnimationController controller = this.controller!;
    final double value = controller.value;
  
    if (value > 1) {
      // Dragged past fully open. Settle back, damping the velocity by the
      // same resistance that was applied while dragging.
      final double overshoot = value - 1;
      final double damped =
          relativeVelocity / (1 + overshoot * _overdragResistance);
      controller.animateWith(
        SpringSimulation(_enterSpring, value, 1, -damped, snapToEnd: true),
      );

      return;
    }
  
    final bool close = switch (relativeVelocity) {
      > _closeVelocity => true,
      < -_closeVelocity => false,
      _ => value < _closePosition,
    };
  
    if (close) {
      _releaseVelocity = relativeVelocity;
      navigator?.pop();
    } else {
      controller.animateWith(
        SpringSimulation(
          _enterSpring,
          value,
          1,
          -relativeVelocity,
          snapToEnd: true,
        ),
      );
    }
  }
  
  @override
  Widget buildPage(
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
  ) {
    return Align(
      alignment: Alignment.bottomCenter,
      child: AnimatedBuilder(
        animation: controller!,
        builder: (context, child) {
          return FractionalTranslation(
            translation: Offset(0, 1 - controller!.value),
            child: child,
          );
        },
        child: Builder(
          builder: (context) {
            // Drag deltas are normalized by the sheet's own height, so the
            // gesture and the route animation share one coordinate space.
            double height() => context.size?.height ?? 1;
  
            return GestureDetector(
              excludeFromSemantics: true,
              onVerticalDragUpdate: (details) {
                _dragBy(details.primaryDelta! / height());
              },
              onVerticalDragEnd: (details) {
                _endDrag(details.velocity.pixelsPerSecond.dy / height());
              },
              onVerticalDragCancel: () {
                _endDrag(0);
              },
              child: SizedBox(
                width: double.infinity,
                child: SheetContainer(
                  child: builder(context),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
  
/// The surface for sheets shown with [showSpringBottomSheet]: white with
/// rounded top corners, matching the old bottom sheet theme.
class SheetContainer extends StatelessWidget {
  const SheetContainer({
    super.key,
    required this.child,
  });
  
  final Widget child;
  
  @override
  Widget build(BuildContext context) {
    return Material(
      type: .transparency,
      child: ClipRRect(
        borderRadius: const .vertical(
          top: Radius.circular(20),
        ),
        child: ColoredBox(
          color: Colors.white,
          child: child,
        ),
      ),
    );
  }
}
  
/// An animation that forwards [parent] with its value clamped to the range
/// 0.0 to 1.0, for consumers such as the modal barrier that should not see
/// values past fully open.
class _ClampedAnimation extends Animation<double>
    with AnimationWithParentMixin<double> {
  _ClampedAnimation(this.parent);
  
  @override
  final Animation<double> parent;
  
  @override
  double get value => parent.value.clamp(0.0, 1.0);
}
```

## Steps

1. Create `lib/widgets/spring_sheet.dart` as in point 1.
2. Change the call in `lib/widgets/vote_buttons.dart` as in point 2.

## Check it

- `flutter analyze` clean; `flutter test` passes (check the vote tests that mark ✓ and pick a cinema).
- `grep -c "showModalBottomSheet" lib/widgets/vote_buttons.dart` → 0; `grep -c "showSpringBottomSheet" lib/widgets/vote_buttons.dart` → 1.
- By eye: mark a film ✓: the sheet slides up with a spring, can be dragged down to close, and tapping a cinema or "Salta" closes it.

## Don't touch

- The `showDialog` pop-ups, other sheets (none), `personal.setSeen`. No new dependencies.

## STOP if

- The article's file needs a package that is not in `pubspec.yaml`.
- Tests that tap a cinema in the sheet fail twice.

## When you're done

Tell the developer the "Dove hai visto…?" sheet now opens with a springy motion and follows the finger when dragged down. Mark any film ✓ to see it.
