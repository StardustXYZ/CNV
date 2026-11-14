import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/models.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/in_sala_page.dart';

import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

/// Saturday 14/11/2026 at 20:00 (see sample() in programme_test.dart).
Future<void> openApp(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.6;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false))));
}

/// The vertical list of the In sala page (the pages side by side scroll too).
Finder pageList() => find.descendant(of: find.byType(InSalaPage), matching: find.byType(Scrollable)).first;

void main() {
  test('titles are found without accents, case or punctuation, also by the cinema title', () {
    const film = Film(id: 1, title: 'Città perduta', rawTitle: 'CITTA\' PERDUTA (V.O.)', status: 'in_sala');
    expect(titleMatches(film, 'citta'), isTrue);
    expect(titleMatches(film, 'PERDUTA v.o'), isTrue);
    expect(titleMatches(film, 'hope'), isFalse);
    expect(titleMatches(film, '  '), isTrue);
  });

  testWidgets('cards: latest arrivals first, today or the next day, times with their end', (tester) async {
    await openApp(tester);

    expect(tester.getTopLeft(find.text('Hope')).dy, lessThan(tester.getTopLeft(find.text('Clayface')).dy)); // 13/11 before 5/11
    expect(find.text('In sala dal 13 novembre'), findsOneWidget);
    expect(find.text('OGGI'), findsOneWidget); // Clayface
    expect(find.text('PROSSIMI SPETTACOLI: DOMANI'), findsOneWidget); // Hope
    expect(find.text('21:00'), findsOneWidget);
    expect(find.text('→22:50'), findsOneWidget); // 100 minutes + 10
    expect(find.text('18:00'), findsNothing); // already started
    expect(find.text('Andromeda River'), findsOneWidget);
    expect(find.textContaining("non ha risposto il sito di Cinema Garden"), findsOneWidget);

    await tester.scrollUntilVisible(find.text('Non più in programmazione (1)'), 300, scrollable: pageList());
    await tester.tap(find.text('Non più in programmazione (1)'));
    await tester.pumpAndSettle();
    expect(find.text('Frankie'), findsOneWidget);
    expect(find.textContaining('uscito dalle sale dal 17 novembre se non ricompare'), findsOneWidget);
  });

  testWidgets('filters by title, genre and cinema', (tester) async {
    await openApp(tester);

    await tester.enterText(find.byType(TextField), 'hop');
    await tester.pumpAndSettle();
    expect(find.text('Hope'), findsOneWidget);
    expect(find.text('Clayface'), findsNothing);
    expect(find.text('1 film'), findsOneWidget);
    await tester.tap(find.text('Togli filtri'));
    await tester.pumpAndSettle();
    expect(find.text('Clayface'), findsOneWidget);

    await tester.tap(find.text('Tutti i generi'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Horror').last);
    await tester.pumpAndSettle();
    expect(find.text('Clayface'), findsOneWidget);
    expect(find.text('Hope'), findsNothing);
    await tester.tap(find.text('Togli filtri'));
    await tester.pumpAndSettle();

    // A cinema: only its films and shows, and no "no longer programmed" list
    await tester.tap(find.text('Tutti i cinema'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cinema Garden').last);
    await tester.pumpAndSettle();
    expect(find.text('Andromeda River'), findsNothing);
    expect(find.text('20:30'), findsOneWidget);
    expect(find.textContaining('Non più in programmazione'), findsNothing);
  });

  testWidgets('the film page: every show by cinema and day', (tester) async {
    await openApp(tester);

    await tester.tap(find.text('Clayface'));
    await tester.pumpAndSettle();
    expect(find.text('Spettacoli'), findsOneWidget);
    expect(find.text('In sala dal 5 novembre'), findsOneWidget);
    expect(find.text('2026 · Horror · 1h 40m'), findsNothing); // no year in the sample
    expect(find.text('Horror · 1h 40m'), findsOneWidget);
    // Garden first (its first show is earlier): today; then Andromeda: today and tomorrow
    expect(tester.getTopLeft(find.text('Cinema Garden')).dy, lessThan(tester.getTopLeft(find.text('Andromeda River')).dy));
    expect(find.text('Oggi'), findsNWidgets(2));
    expect(find.text('Domani'), findsOneWidget);
    expect(find.text('17:00'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Non più in programmazione (1)'), 300, scrollable: pageList());
    await tester.tap(find.text('Non più in programmazione (1)'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Frankie'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Nessuno spettacolo in programma.'), findsOneWidget);
  });
}
