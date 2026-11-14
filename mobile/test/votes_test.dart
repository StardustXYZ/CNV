import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/in_sala_page.dart';
import 'package:cnv/pages/voti_page.dart';
import 'package:cnv/widgets/vote_buttons.dart';

import 'personal_test.dart' show MemoryPersonal;
import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

/// Saturday 14/11/2026 at 20:00, with votes kept in memory.
Future<MemoryPersonal> openApp(WidgetTester tester, {Map<int, String> votes = const {}}) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.6;
  addTearDown(tester.view.reset);
  final personal = MemoryPersonal()..votesById = {...votes};
  await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false)), personal: personal));
  return personal;
}

/// The vote buttons of a film's card in In sala.
Finder votesOf(String title) => find.descendant(
    of: find.ancestor(of: find.text(title), matching: find.byType(FilmCard)), matching: find.byType(VoteButtons));

Finder button(String title, String label) => find.descendant(of: votesOf(title), matching: find.text(label));

/// The film titles listed by In sala.
List<String> titles(WidgetTester tester) =>
    [for (final c in tester.widgetList<FilmCard>(find.byType(FilmCard))) c.film.title];

void main() {
  testWidgets('V and ? on a card; touching it again removes the vote', (tester) async {
    final personal = await openApp(tester);
    await tester.tap(button('Hope', 'V'));
    await tester.pump();
    expect(personal.vote(2), 'V');
    await tester.tap(button('Hope', '?'));
    await tester.pump();
    expect(personal.vote(2), '?');
    await tester.tap(button('Hope', '?'));
    await tester.pump();
    expect(personal.vote(2), isNull);
  });

  testWidgets('✓ asks where it was seen, among the cinemas that show it', (tester) async {
    final personal = await openApp(tester);
    await tester.tap(button('Hope', '✓'));
    await tester.pumpAndSettle();
    final sheet = find.byType(BottomSheet);
    expect(find.descendant(of: sheet, matching: find.text('Dove hai visto Hope?')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text('Cinema Garden')), findsOneWidget);
    expect(find.descendant(of: sheet, matching: find.text('Andromeda River')), findsNothing); // Hope is only at the Garden
    await tester.tap(find.descendant(of: sheet, matching: find.text('Cinema Garden')));
    await tester.pumpAndSettle();
    expect(personal.vote(2), 'S');
    expect(personal.seen[2]!.date, '2026-11-14');
    expect(personal.seen[2]!.cinema, 'garden');
    expect(find.text('✓ Visto il 14 novembre · Cinema Garden'), findsOneWidget);
  });

  testWidgets('"Salta" keeps the ✓ without a cinema', (tester) async {
    final personal = await openApp(tester);
    await tester.ensureVisible(button('Clayface', '✓'));
    await tester.pumpAndSettle();
    await tester.tap(button('Clayface', '✓'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Salta'));
    await tester.pumpAndSettle();
    expect(personal.vote(1), 'S');
    expect(personal.seen[1]!.cinema, isNull);
    expect(find.text('✓ Visto il 14 novembre'), findsOneWidget);
  });

  testWidgets('In sala filters the films by vote', (tester) async {
    await openApp(tester, votes: {1: 'V'});
    expect(titles(tester), ['Hope', 'Clayface']);
    await tester.tap(find.widgetWithText(ChoiceChip, 'V'));
    await tester.pump();
    expect(titles(tester), ['Clayface']);
    await tester.tap(find.widgetWithText(ChoiceChip, 'Da votare'));
    await tester.pump();
    expect(titles(tester), ['Hope']);
    await tester.tap(find.widgetWithText(ChoiceChip, '?'));
    await tester.pump();
    expect(titles(tester), isEmpty);
    expect(find.text('Nessun film in sala con questi filtri.'), findsOneWidget);
    await tester.tap(find.text('Togli filtri'));
    await tester.pump();
    expect(titles(tester), ['Hope', 'Clayface']);
  });

  testWidgets('a vote given on the film page shows up on the card too', (tester) async {
    final personal = await openApp(tester);
    await tester.tap(find.descendant(of: find.byType(FilmCard), matching: find.text('Clayface')));
    await tester.pumpAndSettle();
    await tester.tap(find.descendant(of: find.byType(VoteButtons).last, matching: find.text('V')));
    await tester.pump();
    expect(personal.vote(1), 'V');
    await tester.pageBack();
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ChoiceChip, 'V'));
    await tester.pump();
    expect(titles(tester), ['Clayface']);
  });

  testWidgets('the Voti page counts the votes and offers the copy', (tester) async {
    await openApp(tester, votes: {1: 'V', 2: 'V', 5: 'S'});
    await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Voti')));
    await tester.pumpAndSettle();
    final page = find.byType(VotiPage);
    expect(find.descendant(of: page, matching: find.text('2')), findsOneWidget);
    expect(find.descendant(of: page, matching: find.text('0')), findsOneWidget);
    expect(find.descendant(of: page, matching: find.text('1')), findsOneWidget);
    expect(find.text('Salva una copia dei voti'), findsOneWidget);
    expect(find.text('Ripristina da una copia'), findsOneWidget);
  });
}
