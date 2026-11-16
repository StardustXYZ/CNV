import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/models.dart';
import 'package:cnv/data/programme.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/film_page.dart';
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

  testWidgets("the film page links the film's page on each cinema site, the soonest first", (tester) async {
    await openInUscita(tester);
    await tester.tap(find.text('Avengers'));
    await tester.pumpAndSettle();

    final chips = find.byType(ActionChip);
    await tester.scrollUntilVisible(chips.last, 200, scrollable: find.byType(Scrollable).last);
    expect(find.text('Sui siti dei cinema'), findsOneWidget);
    final names = [for (final c in tester.widgetList<ActionChip>(chips)) (c.label as Text).data];
    expect(names, ['Andromeda River', 'Cinema Garden']); // presale on 16/12, then announced for 18/12

    // Dune has no page on any site: no section
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Dune'));
    await tester.pumpAndSettle();
    expect(find.text('Sui siti dei cinema'), findsNothing);
  });

  test('a film that left without ever being shown says so', () {
    const never = Film(id: 9, title: 'Mai visto', status: 'uscito');
    const left = Film(id: 8, title: 'Visto', status: 'uscito', since: '2026-10-01', left: '2026-11-01');
    expect(FilmPage.statusLine(never, const [], '2026-11-14'), 'Non è arrivato in sala');
    expect(FilmPage.statusLine(left, const [], '2026-11-14'), 'Uscito dalle sale il 1 novembre');
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
