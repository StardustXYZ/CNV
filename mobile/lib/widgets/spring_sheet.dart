import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';

import '../theme.dart';
  
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
  
/// The surface for sheets shown with [showSpringBottomSheet]: the app's dark
/// surface with rounded top corners.
class SheetContainer extends StatelessWidget {
  const SheetContainer({
    super.key,
    required this.child,
  });
  
  final Widget child;
  
  @override
  Widget build(BuildContext context) {
    return Material(
      type: MaterialType.transparency,
      child: ClipRRect(
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(20),
        ),
        child: ColoredBox(
          color: CnvColors.surface,
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
