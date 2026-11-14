/// The Watchlist and Visti lists, their files for Letterboxd and the statistics of the films
/// seen, as in the web version (pageWatchlist, pageVisti, seenStats in phone/app.js).
library;

import 'format.dart';
import 'models.dart';
import 'personal.dart';

/// Films marked V or ? that left the cinemas: they go to the watchlist on Letterboxd.
List<Film> watchlistFilms(CnvData data, PersonalStore p) =>
    [for (final f in data.films) if (f.status == 'uscito' && const ['V', '?'].contains(p.vote(f.id))) f];

/// The ones that go in the next watchlist file: without TMDB they cannot be imported.
List<Film> toExport(CnvData data, PersonalStore p) =>
    [for (final f in watchlistFilms(data, p)) if (!p.exported.containsKey(f.id) && f.tmdbId != null) f];

/// Films marked ✓, the latest seen first.
List<Film> seenFilms(CnvData data, PersonalStore p) => [for (final f in data.films) if (p.vote(f.id) == 'S') f]
  ..sort((a, b) {
    final byDate = (p.seen[b.id]?.date ?? '').compareTo(p.seen[a.id]?.date ?? '');
    return byDate != 0 ? byDate : a.title.compareTo(b.title);
  });

/// The seen films that go in the next diary file: without TMDB they cannot be imported.
List<Film> toDiary(CnvData data, PersonalStore p) =>
    [for (final f in seenFilms(data, p)) if (!p.diary.containsKey(f.id) && f.tmdbId != null) f];

String _quote(String s) => RegExp(r'[",\n]').hasMatch(s) ? '"${s.replaceAll('"', '""')}"' : s;

/// The file for the watchlist import on Letterboxd.
String watchlistCsv(List<Film> films) =>
    '${['tmdbID,Title,Year', for (final f in films) '${f.tmdbId},${_quote(f.title)},${f.year ?? ''}'].join('\n')}\n';

/// The file for "Importa i tuoi dati" on Letterboxd: one diary entry per film, with its day.
String diaryCsv(List<Film> films, Map<int, SeenInfo> seen) => '${[
      'tmdbID,Title,Year,WatchedDate',
      for (final f in films) '${f.tmdbId},${_quote(f.title)},${f.year ?? ''},${seen[f.id]?.date ?? ''}',
    ].join('\n')}\n';

const noCinema = 'Non indicato';
const noGenre = 'Non noto';

/// Numbers and bars of the films seen.
class SeenStats {
  const SeenStats({
    required this.total,
    required this.thisMonth,
    required this.byMonth,
    required this.byCinema,
    required this.byGenre,
  });

  final int total;
  final int thisMonth;
  final List<(String, int)> byMonth; // from the first month with a film to this one, at most 12
  final List<(String, int)> byCinema; // most frequent first, "Non indicato" last
  final List<(String, int)> byGenre; // most seen first, "Non noto" last

  String? get topCinema => byCinema.where((e) => e.$1 != noCinema).firstOrNull?.$1;
  String? get topGenre => byGenre.where((e) => e.$1 != noGenre).firstOrNull?.$1;

  factory SeenStats.of(List<Film> films, Map<int, SeenInfo> seen, CnvData data, String today) {
    Map<String, int> count(Iterable<String> keys) {
      final m = <String, int>{};
      for (final k in keys) {
        m[k] = (m[k] ?? 0) + 1;
      }
      return m;
    }

    List<(String, int)> ranked(Map<String, int> m, String last) => [
          ...([for (final e in m.entries) if (e.key != last) (e.key, e.value)]
            ..sort((a, b) => b.$2 != a.$2 ? b.$2.compareTo(a.$2) : a.$1.compareTo(b.$1))),
          if (m.containsKey(last)) (last, m[last]!),
        ];

    final months = count([for (final f in films) if (seen[f.id]?.date case final d?) d.substring(0, 7)]);
    // Months counted from year 0, as in the web version
    int index(String ym) => int.parse(ym.substring(0, 4)) * 12 + int.parse(ym.substring(5, 7)) - 1;
    final now = index(today);
    var first = months.keys.map(index).fold(now, (a, b) => b < a ? b : a);
    if (first < now - 11) first = now - 11;
    String key(int i) => '${i ~/ 12}-${(i % 12 + 1).toString().padLeft(2, '0')}';
    final cinemas = count([
      for (final f in films)
        if (seen[f.id]?.cinema case final c?) data.cinemasBySlug[c]?.name ?? c else noCinema,
    ]);
    return SeenStats(
      total: films.length,
      thisMonth: months[today.substring(0, 7)] ?? 0,
      byMonth: [for (var i = first; i <= now; i++) ('${shortMonth(i % 12 + 1)} ${i ~/ 12}', months[key(i)] ?? 0)],
      byCinema: ranked(cinemas, noCinema),
      byGenre: ranked(count([for (final f in films) f.genre ?? noGenre]), noGenre),
    );
  }
}
