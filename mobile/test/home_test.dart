import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/changelog.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/data/storage.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/in_sala_page.dart';

import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

void main() {
  testWidgets('a tap on the tab that is already open scrolls its page back to the top', (tester) async {
    // A short screen, so that "In sala" has to scroll
    tester.view.physicalSize = const Size(800, 700);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false))));

    final list = find.descendant(of: find.byType(InSalaPage), matching: find.byType(Scrollable)).first;
    double offset() => tester.state<ScrollableState>(list).position.pixels;

    await tester.drag(list, const Offset(0, -300));
    await tester.pumpAndSettle();
    expect(offset(), greaterThan(0)); // the page really scrolled

    final menu = find.byType(NavigationBar);
    await tester.tap(find.descendant(of: menu, matching: find.text('In sala')));
    await tester.pumpAndSettle();
    expect(offset(), 0);
    expect(tester.widget<NavigationBar>(menu).selectedIndex, 0); // still on the same page
  });

  group('the novelties after an update', () {
    const entries = [
      ChangelogEntry('1.2.0', ['Una cosa nuova', 'Un\'altra cosa']),
    ];

    testWidgets('shown once on the first open after an update', (tester) async {
      final storage = MemoryStorage()..texts['novita.txt'] = '1.1.0';
      final changelog = ChangelogStore(currentVersion: '1.2.0', storage: storage, entries: entries);
      await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false)), changelog: changelog));
      await tester.pumpAndSettle();

      expect(find.text('Novità'), findsOneWidget);
      expect(find.text('Una cosa nuova'), findsOneWidget);
      expect(find.text('Un\'altra cosa'), findsOneWidget);
      expect(storage.texts['novita.txt'], '1.2.0'); // seen: it does not come back

      await tester.tap(find.text('Ok'));
      await tester.pumpAndSettle();
      expect(find.text('Novità'), findsNothing);

      // The next open: the version was already seen
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(CnvApp(
        store: await storeWith(LoadResult(sample(), offline: false)),
        changelog: ChangelogStore(currentVersion: '1.2.0', storage: storage, entries: entries),
      ));
      await tester.pumpAndSettle();
      expect(find.text('Novità'), findsNothing);
    });

    testWidgets('not shown on a first install', (tester) async {
      final storage = MemoryStorage();
      final changelog = ChangelogStore(currentVersion: '1.2.0', storage: storage, entries: entries);
      await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false)), changelog: changelog));
      await tester.pumpAndSettle();

      expect(find.text('Novità'), findsNothing);
      expect(storage.texts['novita.txt'], '1.2.0');
    });
  });
}
