import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:cnv/data/models.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/home.dart';
import 'package:cnv/main.dart';

import 'programme_test.dart' show sample;

/// A data source without network or files: [result] null means "no connection, no copy".
class FakeRepository extends DataRepository {
  FakeRepository(this.result) : super(client: MockClient((_) async => http.Response('', 500)));

  LoadResult? result;

  @override
  Future<LoadResult> load() async => result ?? (throw Exception('offline'));

  @override
  Future<CnvData?> readSaved() async => null;
}

Future<DataStore> storeWith(LoadResult? result, {DateTime? now}) async {
  final store = DataStore(FakeRepository(result), clock: () => now ?? DateTime(2026, 11, 14, 20));
  await store.refresh();
  return store;
}

void main() {
  testWidgets('title, the five pages in the menu and the data status', (tester) async {
    await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false))));

    expect(find.text('CNV'), findsOneWidget);
    expect(find.text('Chi Ni Vidimu'), findsOneWidget);
    final menu = find.byType(NavigationBar);
    for (final page in cnvPages) {
      expect(find.descendant(of: menu, matching: find.text(page.label)), findsOneWidget);
    }
    final made = sample().generatedAt.toLocal();
    expect(find.text('Dati aggiornati il ${made.day}/${made.month} alle ${made.hour.toString().padLeft(2, '0')}:00'),
        findsOneWidget);
    expect(find.text('Clayface'), findsOneWidget); // "In sala" first, with its films
    expect(find.text('Hope'), findsOneWidget);
  });

  testWidgets('the menu and a swipe change the page', (tester) async {
    await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: false))));
    final menu = find.byType(NavigationBar);

    await tester.tap(find.descendant(of: menu, matching: find.text('Visti')));
    await tester.pumpAndSettle();
    expect(find.text(cnvPages[3].description), findsOneWidget);
    expect(tester.widget<NavigationBar>(menu).selectedIndex, 3);

    // Finger to the left: the next page, and the menu follows
    await tester.fling(find.byType(PageView), const Offset(-400, 0), 1500);
    await tester.pumpAndSettle();
    expect(find.text(cnvPages[4].description), findsOneWidget);
    expect(tester.widget<NavigationBar>(menu).selectedIndex, 4);

    await tester.fling(find.byType(PageView), const Offset(400, 0), 1500);
    await tester.pumpAndSettle();
    expect(tester.widget<NavigationBar>(menu).selectedIndex, 3);
  });

  testWidgets('saved copy and old data are pointed out', (tester) async {
    await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(sample(), offline: true))));
    expect(find.textContaining('senza connessione'), findsOneWidget);

    // A new screen (key): the app never swaps its data source, the test does
    await tester.pumpWidget(CnvApp(key: UniqueKey(), store: await storeWith(LoadResult(sample(), offline: false), now: DateTime(2026, 11, 16))));
    await tester.pump();
    expect(find.textContaining('dati vecchi'), findsOneWidget);
  });

  testWidgets('no data at all: the message, and "Riprova" when the network is back', (tester) async {
    final repository = FakeRepository(null);
    final store = DataStore(repository, clock: () => DateTime(2026, 11, 14, 20));
    await store.refresh();
    await tester.pumpWidget(CnvApp(store: store));
    expect(find.textContaining('Non riesco a scaricare i dati'), findsOneWidget);

    repository.result = LoadResult(sample(), offline: false);
    await tester.tap(find.text('Riprova'));
    await tester.pumpAndSettle();
    expect(find.text('Clayface'), findsOneWidget);
  });
}
