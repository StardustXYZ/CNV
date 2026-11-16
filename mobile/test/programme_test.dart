import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/models.dart';
import 'package:cnv/data/programme.dart';

/// Saturday 14/11/2026: Clayface today and tomorrow, Hope only tomorrow, Dune announced,
/// Avengers in presale in December.
CnvData sample() => CnvData.fromJson({
      'generated_at': '2026-11-14T03:00+01:00',
      'settings': {'days_to_uscito': 7, 'days_to_uscito_evento': 3, 'show_extra_minutes': 10},
      'cinemas': [
        {'slug': 'andromeda', 'name': 'Andromeda River', 'url': 'https://andromeda.example'},
        {'slug': 'garden', 'name': 'Cinema Garden', 'url': 'https://garden.example'},
      ],
      'films': [
        {'id': 1, 'title': 'Clayface', 'status': 'in_sala', 'runtime': 100, 'genre': 'Horror', 'since': '2026-11-05'},
        {'id': 2, 'title': 'Hope', 'status': 'in_sala', 'genre': 'Fantascienza', 'since': '2026-11-13'},
        {'id': 3, 'title': 'Dune', 'status': 'in_uscita'},
        {'id': 4, 'title': 'Avengers', 'status': 'in_uscita'},
        {'id': 5, 'title': 'Frankie', 'status': 'in_sala', 'last_seen': '2026-11-10'}, // no shows left
      ],
      'shows': [
        {'f': 1, 'c': 'andromeda', 'd': '2026-11-14', 't': '18:00', 's': 'Sala 1', 'u': ''}, // started
        {'f': 1, 'c': 'andromeda', 'd': '2026-11-14', 't': '21:00', 's': 'Sala 1', 'u': 'https://buy/1'},
        {'f': 1, 'c': 'garden', 'd': '2026-11-14', 't': '20:30', 's': 'Sala A', 'u': 'https://buy/2'},
        {'f': 1, 'c': 'garden', 'd': '2026-11-14', 't': '20:30', 's': 'Sala A', 'u': 'https://buy/2'}, // repeated
        {'f': 1, 'c': 'andromeda', 'd': '2026-11-15', 't': '17:00', 's': 'Sala 2', 'u': ''},
        {'f': 2, 'c': 'garden', 'd': '2026-11-15', 't': '21:15', 's': 'Sala B', 'u': ''},
        {'f': 4, 'c': 'andromeda', 'd': '2026-12-16', 't': '20:30', 's': 'Sala 3', 'u': ''},
        {'f': 5, 'c': 'andromeda', 'd': '2026-11-10', 't': '21:00', 's': 'Sala 1', 'u': ''}, // past
      ],
      'coming': [
        {'f': 3, 'c': 'garden', 'd': null},
        {'f': 4, 'c': 'garden', 'd': '2026-12-18'},
      ],
      'pages': [
        {'f': 4, 'c': 'andromeda', 'u': 'https://andromeda.example/avengers'},
        {'f': 4, 'c': 'garden', 'u': 'https://garden.example/avengers'},
      ],
      'merged': {'42': 1},
      'not_updated': {'garden': '2026-11-13'},
    });

void main() {
  final now = DateTime(2026, 11, 14, 20, 0);

  test('the file is read with its extra lists', () {
    final data = sample();
    expect(data.filmsById[1]!.title, 'Clayface');
    expect(data.merged, {42: 1});
    expect(data.notUpdated, {'garden': '2026-11-13'});
    expect(data.sitePages[4], {'andromeda': 'https://andromeda.example/avengers', 'garden': 'https://garden.example/avengers'});
    expect(data.sitePages[1], isNull);
    expect(CnvData.fromJson({'generated_at': '2026-11-14T03:00+01:00'}).sitePages, isEmpty); // an older file
    expect(data.generatedAt.toUtc(), DateTime.utc(2026, 11, 14, 2, 0));
  });

  test('next shows: the rest of today, else the next day with shows', () {
    final data = sample();
    final p = Programme.build(data, now);
    final clay = p.nextShows(data.filmsById[1]!)!;
    expect(clay.day, '2026-11-14');
    expect(clay.byCinema.keys.toSet(), {'andromeda', 'garden'});
    final andromeda = sortedSalas(clay.byCinema['andromeda']!);
    expect(andromeda.single.value.map((s) => s.start), [DateTime(2026, 11, 14, 21, 0)]); // 18:00 already started
    expect(andromeda.single.value.single.end, DateTime(2026, 11, 14, 22, 50)); // 100 min + 10
    expect(sortedSalas(clay.byCinema['garden']!).single.value, hasLength(1)); // the repeated 20:30 once

    expect(p.nextShows(data.filmsById[2]!)!.day, '2026-11-15'); // Hope: tomorrow
    expect(p.nextShows(data.filmsById[5]!), isNull); // Frankie: nothing left
  });

  test('counts and cinemas of In sala and In uscita', () {
    final data = sample();
    final p = Programme.build(data, now);
    expect(p.inSala.map((f) => f.title), ['Clayface', 'Hope']);
    expect(p.inUscita.map((f) => f.title), ['Dune', 'Avengers']);
    final avengers = p.cinemaReleases(data.filmsById[4]!);
    expect([for (final r in avengers) (r.cinema, r.date, r.announced)], [
      ('andromeda', '2026-12-16', false),
      ('garden', '2026-12-18', true),
    ]);
    expect(p.cinemaReleases(data.filmsById[3]!).single.date, isNull); // announced without a date
  });

  test('only one cinema', () {
    final data = sample();
    final p = Programme.build(data, now, cinema: 'garden');
    expect(p.inSala.map((f) => f.title), ['Clayface', 'Hope']);
    expect(p.nextShows(data.filmsById[1]!)!.byCinema.keys, ['garden']);
    expect(p.inUscita.map((f) => f.title), ['Dune', 'Avengers']); // announced at the Garden
  });

  test("today's real data.json is read without errors", () {
    final text = File('test/fixtures/data.json').readAsStringSync();
    final data = CnvData.fromJson(jsonDecode(text) as Map<String, dynamic>);
    expect(data.films, isNotEmpty);
    expect(data.cinemas.length, 5);
    for (final s in data.shows) {
      expect(data.cinemasBySlug.containsKey(s.cinema), isTrue);
    }
    // Every show's film is in the list, and the rules run on all of them
    final p = Programme.build(data, data.generatedAt.toLocal());
    expect(p.inSala, isNotEmpty);
  });
}
