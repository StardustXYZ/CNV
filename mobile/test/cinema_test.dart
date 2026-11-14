import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';

import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

/// Saturday 14/11/2026 (see sample() in programme_test.dart), at 20:00 unless said otherwise.
Future<void> openApp(WidgetTester tester, {DateTime? now}) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.6;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false), now: now)));
}

Finder inMenu(String text) => find.descendant(of: find.byType(Drawer), matching: find.text(text));

Future<void> openMenu(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Open navigation menu'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the menu lists the cinemas with the films they still show today', (tester) async {
    await openApp(tester);
    await openMenu(tester);

    expect(inMenu('Andromeda River'), findsOneWidget);
    expect(inMenu('Cinema Garden'), findsOneWidget);
    // Clayface still today at both (21:00 and 20:30)
    expect(find.descendant(of: find.byType(Drawer), matching: find.text('1')), findsNWidgets(2));
  });

  testWidgets('cinema page: days in the calendar and the films of the chosen day', (tester) async {
    await openApp(tester);
    await openMenu(tester);
    await tester.tap(inMenu('Andromeda River'));
    await tester.pumpAndSettle();

    expect(find.widgetWithText(AppBar, 'Andromeda River'), findsOneWidget);
    expect(find.text('Oggi'), findsOneWidget);
    expect(find.text('Domani'), findsOneWidget);
    expect(find.text('Mer 16/12'), findsOneWidget); // Avengers in presale
    expect(find.text('Clayface'), findsOneWidget);
    expect(find.text('21:00'), findsOneWidget);
    expect(find.textContaining('ecco quelli di'), findsNothing);

    await tester.tap(find.text('Mer 16/12'));
    await tester.pumpAndSettle();
    expect(find.text('Avengers'), findsOneWidget);
    expect(find.text('Clayface'), findsNothing);
  });

  testWidgets('when today is over, the next day with a notice', (tester) async {
    await openApp(tester, now: DateTime(2026, 11, 14, 23));
    await openMenu(tester);
    await tester.tap(inMenu('Andromeda River'));
    await tester.pumpAndSettle();

    expect(find.text('Oggi'), findsNothing);
    expect(find.text('Oggi non ci sono altri spettacoli: ecco quelli di domani.'), findsOneWidget);
    expect(find.text('17:00'), findsOneWidget);
  });

  testWidgets("a cinema whose site did not answer, and a cinema's name opening its page", (tester) async {
    await openApp(tester);
    await tester.tap(find.text('Cinema Garden').first); // on the Clayface card
    await tester.pumpAndSettle();
    expect(find.widgetWithText(AppBar, 'Cinema Garden'), findsOneWidget);
    expect(find.textContaining('non ha risposto il sito di Cinema Garden'), findsOneWidget);
    expect(find.text('20:30'), findsOneWidget);
  });
}
