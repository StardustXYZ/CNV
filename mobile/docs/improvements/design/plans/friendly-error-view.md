# Fix: A broken widget shows an empty grey box

> Follow the steps in order. Run every check. If anything in "STOP if"
> happens, stop and report instead of improvising.

- **Link**: https://flutterpro.design/details/md/friendly-error-view
- **Needs new dependency**: none

## Why

When a widget fails to build, release builds show an empty grey box and the user does not know what happened. Show a friendly message in the app's colors instead, and let a long press copy the real error (useful when a friend reports a problem).

## Where

`grep -rn "ErrorWidget.builder" lib` finds nothing.

```dart
// lib/main.dart:~24-25 — current
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
```

## The fix

1. Create `lib/widgets/friendly_error_view.dart` with the article's file below, with these adaptations:
   - Texts in Italian: `'Something went wrong'` → `'Qualcosa è andato storto'`; `'Restarting the app should fix it.'` → `'Riavvia l'app: di solito basta.'` (watch the quote); the `Semantics` label `'Something went wrong. Restarting the app should fix it.'` → `'Qualcosa è andato storto. Riavviare l'app di solito risolve.'`.
   - Colors: the article takes them from `Theme.of(context).colorScheme` (`primaryContainer` etc.); keep that (the app theme is dark violet, it fits). Do not hard-code other colors.
   - The article file may use Dart's dot shorthand (e.g. `.center`, `.ltr`): this project's SDK (`^3.9.2`) does not support it. Replace every shorthand with the full name (e.g. `MainAxisAlignment.center`). `flutter analyze` shows each one.
2. In `lib/main.dart` add `import 'widgets/friendly_error_view.dart';` and, as the second line of `main()` (after `WidgetsFlutterBinding.ensureInitialized();`):

```dart
  ErrorWidget.builder = (details) => FriendlyErrorView(details: details);
```

### The article's file (verbatim)

```dart
import 'dart:async';
  
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
  
/// Friendly replacement for Flutter's red error screen, installed via
/// [ErrorWidget.builder]. Release builds show no technical details; debug
/// builds add the exception and stack trace. A long press anywhere copies
/// the details to the clipboard.
///
/// Adapts to the space the broken widget occupied: a full layout when there
/// is room, an icon-only badge inside small slots.
class FriendlyErrorView extends StatefulWidget {
  const FriendlyErrorView({
    super.key,
    required this.details,
  });
  
  final FlutterErrorDetails details;
  
  @override
  State<FriendlyErrorView> createState() => _FriendlyErrorViewState();
}
  
class _FriendlyErrorViewState extends State<FriendlyErrorView> {
  Timer? _timer;
  bool _copied = false;
  
  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
  
  Future<void> _copy() async {
    HapticFeedback.mediumImpact();
  
    await Clipboard.setData(
      ClipboardData(
        text:
            '${widget.details.exceptionAsString()}\n\n${widget.details.stack}',
      ),
    );
  
    if (!mounted) return;
  
    setState(() => _copied = true);
  
    _timer?.cancel();
    _timer = Timer(const Duration(milliseconds: 2600), () {
      if (mounted) setState(() => _copied = false);
    });
  }
  
  @override
  Widget build(BuildContext context) {
    final ColorScheme cs = Theme.of(context).colorScheme;
  
    // The view can land anywhere in the tree, including where no Material or
    // Directionality ancestor exists, so it provides its own. The transparent
    // Material also prevents the yellow "missing Material" text underlines.
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Material(
        type: MaterialType.transparency,
        child: Semantics(
          container: true,
          label: 'Something went wrong. Restarting the app should fix it.',
          child: ExcludeSemantics(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onLongPress: _copy,
              child: LayoutBuilder(
                builder: (context, c) {
                  final bool full =
                      c.maxHeight.isFinite &&
                      c.maxHeight >= 320 &&
                      c.maxWidth.isFinite &&
                      c.maxWidth >= 300;
  
                  // Only fill bounded axes; under unbounded constraints
                  // (lists, FittedBox) the view sizes to its content.
                  return Container(
                    width: c.hasBoundedWidth ? c.maxWidth : null,
                    height: c.hasBoundedHeight ? c.maxHeight : null,
                    decoration: BoxDecoration(
                      color: cs.primaryContainer,
                      borderRadius: BorderRadius.circular(full ? 0 : 28),
                    ),
                    child: full
                        ? _FullView(
                            details: widget.details,
                            copied: _copied,
                          )
                        : _CompactView(
                            details: widget.details,
                            copied: _copied,
                          ),
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}
  
class _FullView extends StatelessWidget {
  const _FullView({
    required this.details,
    required this.copied,
  });
  
  final FlutterErrorDetails details;
  final bool copied;
  
  @override
  Widget build(BuildContext context) {
    final ColorScheme cs = Theme.of(context).colorScheme;
    final TextTheme tt = Theme.of(context).textTheme;
  
    final Widget header = Column(
      mainAxisSize: .min,
      children: [
        _Badge(
          size: 104,
          copied: copied,
        ),
        const SizedBox(height: 24),
        Text(
          'Something went wrong',
          textAlign: TextAlign.center,
          style: tt.titleLarge?.copyWith(
            color: cs.onPrimaryContainer,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Restarting the app should fix it.',
          textAlign: TextAlign.center,
          style: tt.bodyMedium?.copyWith(
            color: cs.onPrimaryContainer.withValues(alpha: 0.75),
          ),
        ),
      ],
    );
  
    // Centered while the content fits, scrollable once it doesn't: the
    // sliver forces the child to at least viewport height, and the centered
    // column simply grows past it when the debug stack trace is long.
    return CustomScrollView(
      slivers: [
        SliverFillRemaining(
          hasScrollBody: false,
          child: Padding(
            // Clear the status bar and home indicator; the view has no
            // Scaffold or SafeArea above it (and possibly no MediaQuery).
            padding: EdgeInsets.fromLTRB(
              32,
              (MediaQuery.maybePaddingOf(context)?.top ?? 0) + 32,
              32,
              (MediaQuery.maybePaddingOf(context)?.bottom ?? 0) + 32,
            ),
            child: Column(
              mainAxisAlignment: .center,
              children: [
                header,
                if (kDebugMode) ...[
                  const SizedBox(height: 32),
                  _DebugText(
                    '${details.exceptionAsString()}\n\n${details.stack}',
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}
  
class _CompactView extends StatelessWidget {
  const _CompactView({
    required this.details,
    required this.copied,
  });
  
  final FlutterErrorDetails details;
  final bool copied;
  
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Column(
            mainAxisSize: .min,
            children: [
              _Badge(
                size: 48,
                copied: copied,
              ),
              if (kDebugMode) ...[
                const SizedBox(height: 8),
                SizedBox(
                  width: 240,
                  child: _DebugText(
                    details.exceptionAsString(),
                    maxLines: 2,
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
  
/// The badge briefly swaps its "!" for a check after the hidden long-press
/// copy gesture, so regular users never see a hint.
class _Badge extends StatelessWidget {
  const _Badge({
    required this.size,
    required this.copied,
  });
  
  final double size;
  final bool copied;
  
  @override
  Widget build(BuildContext context) {
    final ColorScheme cs = Theme.of(context).colorScheme;
  
    return Container(
      width: size,
      height: size,
      decoration: ShapeDecoration(
        color: cs.primary,
        // A soft flower built with the SDK's StarBorder, so this file needs
        // no shape package.
        shape: const StarBorder(
          points: 12,
          innerRadiusRatio: 0.8,
          pointRounding: 0.7,
          valleyRounding: 0.3,
        ),
      ),
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 200),
        child: Icon(
          copied ? Icons.check_rounded : Icons.priority_high_rounded,
          key: ValueKey<bool>(copied),
          color: cs.onPrimary,
          size: size * 0.4,
        ),
      ),
    );
  }
}
  
/// Exception text shown only in debug builds.
class _DebugText extends StatelessWidget {
  const _DebugText(this.text, {this.maxLines, this.textAlign});
  
  final String text;
  final int? maxLines;
  final TextAlign? textAlign;
  
  @override
  Widget build(BuildContext context) {
    final ColorScheme cs = Theme.of(context).colorScheme;

    return Text(
      text,
      maxLines: maxLines,
      textAlign: textAlign,
      overflow: maxLines == null ? TextOverflow.fade : TextOverflow.ellipsis,
      style: TextStyle(
        fontFamily: 'monospace',
        fontFamilyFallback: const ['Menlo', 'Courier'],
        fontSize: 12,
        color: cs.onPrimaryContainer.withValues(alpha: 0.6),
      ),
    );
  }
}
```

## Steps

1. Create the file with the code above, adapted as in point 1.
2. Edit `lib/main.dart` as in point 2.

## Check it

- `flutter analyze` clean (expand every dot shorthand it reports); `flutter test` passes.
- `grep -c "ErrorWidget.builder" lib/main.dart` → 1.
- By eye (hot restart): temporarily add `throw Exception('prova');` inside the `build` of a small widget, e.g. `CnvTitle`, run: the broken spot shows the friendly box; long-press copies the text. REMOVE the test throw afterwards (`grep -rn "prova" lib` → nothing).

## Don't touch

- Any other widget, the error handling of the sync. No new dependencies.

## STOP if

- The article's file needs a package that is not in `pubspec.yaml`.
- The test throw cannot be removed cleanly. A check fails twice.

## When you're done

Tell the developer that, if a part of the app ever breaks, users see a friendly message instead of a grey box, and that a long press on it copies the real error. 
