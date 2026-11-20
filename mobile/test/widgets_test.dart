import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';
import 'package:cnv/theme.dart';
import 'package:cnv/widgets/friendly_error_view.dart';
import 'package:cnv/widgets/spring_sheet.dart';

import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

void main() {
  testWidgets('a widget that breaks shows the friendly message, and a long press copies the error', (tester) async {
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied = (call.arguments as Map)['text'] as String?;
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));

    await tester.pumpWidget(MaterialApp(
      theme: cnvTheme(),
      home: Scaffold(
        body: FriendlyErrorView(details: FlutterErrorDetails(exception: Exception('boom'), stack: StackTrace.current)),
      ),
    ));
    expect(find.text('Qualcosa è andato storto'), findsOneWidget);

    await tester.longPress(find.byType(FriendlyErrorView));
    await tester.pump();
    expect(copied, contains('boom'));
    await tester.pump(const Duration(seconds: 3)); // the "copied" mark goes away by itself
  });

  group('the sheet that opens from the bottom', () {
    Future<void> open(WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () => showSpringBottomSheet<void>(
                  context: context,
                  builder: (_) => const SizedBox(height: 200, child: Center(child: Text('contenuto'))),
                ),
                child: const Text('apri'),
              ),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('apri'));
      await tester.pumpAndSettle();
      expect(find.text('contenuto'), findsOneWidget);
    }

    testWidgets('closes when dragged down', (tester) async {
      await open(tester);
      await tester.fling(find.text('contenuto'), const Offset(0, 400), 1500);
      await tester.pumpAndSettle();
      expect(find.text('contenuto'), findsNothing);
    });

    testWidgets('stays open after a short, slow drag, and closes with a tap outside', (tester) async {
      await open(tester);
      await tester.drag(find.text('contenuto'), const Offset(0, 20));
      await tester.pumpAndSettle();
      expect(find.text('contenuto'), findsOneWidget);

      await tester.tapAt(const Offset(10, 10)); // the dark area above the sheet
      await tester.pumpAndSettle();
      expect(find.text('contenuto'), findsNothing);
    });
  });

  testWidgets('the system text size is followed only up to x1.1', (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2.0;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false))));
    final context = tester.element(find.byType(NavigationBar));
    expect(MediaQuery.textScalerOf(context).scale(10), closeTo(11, 0.001));
  });
}
