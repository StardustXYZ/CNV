import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/programme.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/in_uscita_page.dart';

import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

/// Saturday 14/11/2026 at 20:00 (see sample() in programme_test.dart): Avengers from
/// 16/12 (presale at Andromeda, announced at the Garden for 18/12), Dune announced undated.
Future<void> openInUscita(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.6;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false))));
  await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('In uscita')));
  await tester.pumpAndSettle();
}

void main() {
  test('coming films: the soonest first, undated last, with the search', () {
    final programme = Programme.build(sample(), DateTime(2026, 11, 14, 20));
    final films = comingFilms(programme, '');
    expect([for (final c in films) (c.film.title, c.first)], [('Avengers', '2026-12-16'), ('Dune', null)]);
    expect([for (final c in comingFilms(programme, 'dun')) c.film.title], ['Dune']);
  });

  testWidgets('the list: dates as headers, cinemas with their own date', (tester) async {
    await openInUscita(tester);

    expect(find.text('Dal 16 dicembre'), findsOneWidget);
    expect(find.text('Data da definire'), findsOneWidget);
    expect(tester.getTopLeft(find.text('Avengers')).dy, lessThan(tester.getTopLeft(find.text('Dune')).dy));
    expect(find.text('dal 18 dicembre'), findsOneWidget); // the Garden starts later
    expect(find.text('data da definire'), findsOneWidget); // Dune at the Garden

    await tester.enterText(find.byType(TextField), 'aveng');
    await tester.pumpAndSettle();
    expect(find.text('Dune'), findsNothing);
    await tester.enterText(find.byType(TextField), 'zzz');
    await tester.pumpAndSettle();
    expect(find.text('Nessun film in uscita con questo titolo.'), findsOneWidget);
  });

  testWidgets('the calendar: this month first, arrows up to the last release', (tester) async {
    await openInUscita(tester);
    await tester.tap(find.text('Calendario'));
    await tester.pumpAndSettle();

    expect(find.text('Novembre 2026'), findsOneWidget);
    expect(find.text('LUN'), findsOneWidget);
    final previous = tester.widget<IconButton>(find.widgetWithIcon(IconButton, Icons.chevron_left));
    expect(previous.onPressed, isNull); // nothing before this month
    expect(find.byTooltip('Avengers'), findsNothing);
    expect(find.text('Dune'), findsOneWidget); // undated, under the calendar

    await tester.tap(find.byTooltip('Mese successivo'));
    await tester.pumpAndSettle();
    expect(find.text('Dicembre 2026'), findsOneWidget);
    expect(find.byTooltip('Avengers'), findsOneWidget);
    final next = tester.widget<IconButton>(find.widgetWithIcon(IconButton, Icons.chevron_right));
    expect(next.onPressed, isNull); // no releases later

    await tester.tap(find.byTooltip('Avengers'));
    await tester.pumpAndSettle();
    expect(find.text('In uscita dal 16 dicembre'), findsOneWidget); // the film page
  });
}
