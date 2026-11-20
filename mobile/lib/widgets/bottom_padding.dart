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
