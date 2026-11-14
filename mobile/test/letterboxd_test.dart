import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/letterboxd.dart';
import 'package:cnv/data/models.dart';
import 'package:cnv/data/personal.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/visti_page.dart';
import 'package:cnv/pages/watchlist_page.dart';
import 'package:cnv/widgets/letterboxd_widgets.dart';

import 'personal_test.dart' show MemoryPersonal;
import 'widget_test.dart' show storeWith;

/// Films that left the cinemas, one without TMDB, and some seen ones. Today: 14/11/2026.
CnvData gone() => CnvData.fromJson({
      'generated_at': '2026-11-14T03:00+01:00',
      'cinemas': [
        {'slug': 'andromeda', 'name': 'Andromeda River', 'url': 'https://andromeda.example'},
        {'slug': 'garden', 'name': 'Cinema Garden', 'url': 'https://garden.example'},
      ],
      'films': [
        {'id': 1, 'title': 'Old, "the" film', 'tmdb': 101, 'year': 2026, 'status': 'uscito', 'left': '2026-11-01', 'genre': 'Horror'},
        {'id': 2, 'title': 'Nebula', 'tmdb': 102, 'year': 2025, 'status': 'uscito', 'genre': 'Fantascienza'},
        {'id': 3, 'title': 'Senza Tmdb', 'status': 'uscito'},
        {'id': 4, 'title': 'Still on', 'tmdb': 104, 'status': 'in_sala'},
        {'id': 5, 'title': 'Exported', 'tmdb': 105, 'status': 'uscito'},
      ],
      'shows': [],
      'coming': [],
      'merged': <String, dynamic>{},
      'not_updated': <String, dynamic>{},
    });

MemoryPersonal votes() => MemoryPersonal()
  ..votesById = {1: 'V', 2: 'S', 3: '?', 4: 'V', 5: 'V'}
  ..exported = {5: '2026-10-20'}
  ..seen = {2: const SeenInfo('2026-11-08', 'garden')};

void main() {
  group('lists and files', () {
    test('watchlist: V or ? films that left; without TMDB or already exported stay out of the file', () {
      final data = gone(), p = votes();
      expect(watchlistFilms(data, p).map((f) => f.id), [1, 3, 5]);
      expect(toExport(data, p).map((f) => f.id), [1]);
      expect(watchlistCsv(toExport(data, p)), 'tmdbID,Title,Year\n101,"Old, ""the"" film",2026\n');
    });

    test('seen films, the latest first, and the diary file with the day', () {
      final data = gone(), p = votes()
        ..votesById[4] = 'S'
        ..seen[4] = const SeenInfo('2026-11-12');
      expect(seenFilms(data, p).map((f) => f.id), [4, 2]);
      p.diary[4] = '2026-11-13';
      expect(toDiary(data, p).map((f) => f.id), [2]);
      expect(diaryCsv(toDiary(data, p), p.seen), 'tmdbID,Title,Year,WatchedDate\n102,Nebula,2025,2026-11-08\n');
    });

    test('statistics: months up to this one, cinemas and genres with the unknown ones last', () {
      final data = gone();
      final films = [for (final id in [1, 2, 3, 5]) data.filmsById[id]!];
      final seen = {
        1: const SeenInfo('2026-09-03', 'andromeda'),
        2: const SeenInfo('2026-11-08', 'garden'),
        3: const SeenInfo('2026-11-10'),
        5: const SeenInfo('2026-11-11', 'garden'),
      };
      final s = SeenStats.of(films, seen, data, '2026-11-14');
      expect(s.total, 4);
      expect(s.thisMonth, 3);
      expect(s.byMonth, [('Set 2026', 1), ('Ott 2026', 0), ('Nov 2026', 3)]);
      expect(s.byCinema, [('Cinema Garden', 2), ('Andromeda River', 1), (noCinema, 1)]);
      expect(s.topCinema, 'Cinema Garden');
      expect(s.byGenre, [('Fantascienza', 1), ('Horror', 1), (noGenre, 2)]);
      expect(s.topGenre, 'Fantascienza');
    });

    test('at most the last 12 months', () {
      final data = gone();
      final s = SeenStats.of([data.filmsById[1]!], {1: const SeenInfo('2024-01-05')}, data, '2026-11-14');
      expect(s.byMonth.length, 12);
      expect(s.byMonth.first, ('Dic 2025', 0));
    });

    test('marking imported and "Esporta di nuovo"', () async {
      final p = votes();
      await p.markExported([1], '2026-11-14');
      expect(p.exported[1], '2026-11-14');
      await p.exportAgain(1);
      expect(p.exported.containsKey(1), isFalse);
      await p.markDiary([2], '2026-11-14');
      expect(p.diary[2], '2026-11-14');
      await p.diaryAgain(2);
      expect(p.diary, isEmpty);
    });

    test('a ✓ from an old web copy without a day gets one when corrected', () async {
      final p = MemoryPersonal()..votesById = {2: 'S'};
      await p.setSeen(2, cinema: 'garden');
      expect(p.seen[2]!.date, isNull);
      await p.setSeen(2, date: '2026-11-01');
      expect(p.seen[2]!.date, '2026-11-01');
      expect(p.seen[2]!.cinema, 'garden');
    });
  });

  group('pages', () {
    late List<(String, String)> shared;

    setUp(() {
      shared = [];
      shareTextFile = (context, name, content, mime) async => shared.add((name, content));
    });

    Future<MemoryPersonal> open(WidgetTester tester, String page) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.6;
      addTearDown(tester.view.reset);
      final personal = votes();
      await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(gone(), offline: false)), personal: personal));
      await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text(page)));
      await tester.pumpAndSettle();
      return personal;
    }

    testWidgets('Watchlist: the file, the films without TMDB, and the ones already exported', (tester) async {
      final personal = await open(tester, 'Watchlist');
      final page = find.byType(WatchlistPage);
      expect(find.descendant(of: page, matching: find.text('Da esportare (1)')), findsOneWidget);
      expect(find.descendant(of: page, matching: find.text('Old, "the" film (2026)')), findsOneWidget);
      expect(find.descendant(of: page, matching: find.textContaining('1 film senza abbinamento TMDB')), findsOneWidget);
      expect(find.descendant(of: page, matching: find.text('Già esportati (1)')), findsOneWidget);

      await tester.tap(find.text('Scarica CSV per Letterboxd'));
      await tester.pump();
      expect(shared.single.$1, 'letterboxd_watchlist_2026-11-14.csv');
      expect(shared.single.$2, contains('101,"Old, ""the"" film",2026'));

      await tester.tap(find.text('Li ho importati su Letterboxd'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sì, importati'));
      await tester.pumpAndSettle();
      expect(personal.exported[1], '2026-11-14');
      expect(find.text('Già esportati (2)'), findsOneWidget);
      expect(find.text('Scarica CSV per Letterboxd'), findsNothing);

      await tester.tap(find.text('Già esportati (2)'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Esporta di nuovo').first);
      await tester.pumpAndSettle();
      expect(personal.exported.containsKey(1), isFalse);
      expect(find.text('Da esportare (1)'), findsOneWidget);
    });

    testWidgets('Visti: statistics, the diary file, and the cinema corrected', (tester) async {
      final personal = await open(tester, 'Visti');
      final page = find.byType(VistiPage);
      expect(find.descendant(of: page, matching: find.text('Da mettere nel diario (1)')), findsOneWidget);
      expect(find.descendant(of: page, matching: find.byType(SeenStatsView)), findsOneWidget);
      expect(find.descendant(of: page, matching: find.text('cinema più frequentato')), findsOneWidget);

      await tester.tap(find.text('Scarica CSV per il diario'));
      await tester.pump();
      expect(shared.single.$2, 'tmdbID,Title,Year,WatchedDate\n102,Nebula,2025,2026-11-08\n');

      await tester.scrollUntilVisible(find.text('8 novembre'), 300,
          scrollable: find.descendant(of: page, matching: find.byType(Scrollable)).first);
      await tester.tap(find.descendant(of: page, matching: find.text('Cinema Garden')).last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Andromeda River').last);
      await tester.pumpAndSettle();
      expect(personal.seen[2]!.cinema, 'andromeda');
      expect(personal.seen[2]!.date, '2026-11-08');

      await tester.tap(find.text('Li ho importati su Letterboxd'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Sì, importati'));
      await tester.pumpAndSettle();
      expect(personal.diary[2], '2026-11-14');
      expect(find.text('Nel diario di Letterboxd'), findsOneWidget);
    });

    testWidgets('empty pages say when films will appear', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.6;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(CnvApp(store: await storeWith(LoadResult(gone(), offline: false)), personal: MemoryPersonal()));
      await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Watchlist')));
      await tester.pumpAndSettle();
      expect(find.textContaining('Nessun film da esportare per ora.'), findsOneWidget);
      await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Visti')));
      await tester.pumpAndSettle();
      expect(find.textContaining('Nessun film visto per ora.'), findsOneWidget);
    });
  });
}
