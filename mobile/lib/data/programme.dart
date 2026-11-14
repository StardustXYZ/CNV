/// The shows not started yet, grouped as the pages need them (buildContext in phone/app.js).
library;

import 'models.dart';
import 'schedule.dart';

class UpcomingShow {
  const UpcomingShow({required this.start, required this.url, this.end});

  final DateTime start;
  final DateTime? end; // estimated from the runtime
  final String url;
}

/// The next shows of a film: the rest of today, or the next day with shows when today is over.
class NextShows {
  const NextShows(this.day, this.byCinema);

  final String day;
  final Map<String, Map<String, List<UpcomingShow>>> byCinema; // cinema slug -> sala -> shows
}

/// A cinema that has (or announces) a film, with its first date.
class CinemaRelease {
  const CinemaRelease(this.cinema, this.date, {this.announced = false});

  final String cinema;
  final String? date; // null: announced without a date
  final bool announced; // only in a coming-soon list, no shows yet
}

class Programme {
  Programme._(this.data, this.now, this.day, this._upcoming, this._firstByCinema, this.byCinemaDay, this._announced);

  final CnvData data;
  final DateTime now;
  final String day; // programme day in progress
  final Map<int, Map<String, Map<String, Map<String, List<UpcomingShow>>>>> _upcoming; // film -> day -> cinema -> sala
  final Map<int, Map<String, String>> _firstByCinema; // film -> cinema -> first upcoming day
  final Map<String, Map<String, Map<int, Map<String, List<UpcomingShow>>>>> byCinemaDay; // cinema -> day -> film -> sala
  final Map<int, Map<String, List<String>>> _announced; // film -> cinema -> announced dates

  /// Only the shows still to come at [now]; with [cinema], only that cinema's.
  factory Programme.build(CnvData data, DateTime now, {String? cinema}) {
    final day = programmeDay(now);
    final upcoming = <int, Map<String, Map<String, Map<String, List<UpcomingShow>>>>>{};
    final firstByCinema = <int, Map<String, String>>{};
    final byCinemaDay = <String, Map<String, Map<int, Map<String, List<UpcomingShow>>>>>{};
    for (final s in data.shows) {
      if (s.day.compareTo(day) < 0 || (cinema != null && s.cinema != cinema)) continue;
      final start = showStart(s.day, s.time);
      if (s.day == day && start.isBefore(now)) continue; // already started
      final show = UpcomingShow(
        start: start,
        end: showEnd(start, data.filmsById[s.filmId], data.settings),
        url: s.url.isNotEmpty ? s.url : (data.cinemasBySlug[s.cinema]?.url ?? ''),
      );
      upcoming.putIfAbsent(s.filmId, () => {}).putIfAbsent(s.day, () => {}).putIfAbsent(s.cinema, () => {})
          .putIfAbsent(s.sala, () => []).add(show);
      byCinemaDay.putIfAbsent(s.cinema, () => {}).putIfAbsent(s.day, () => {}).putIfAbsent(s.filmId, () => {})
          .putIfAbsent(s.sala, () => []).add(show);
      final firsts = firstByCinema.putIfAbsent(s.filmId, () => {});
      final known = firsts[s.cinema];
      if (known == null || s.day.compareTo(known) < 0) firsts[s.cinema] = s.day;
    }
    final announced = <int, Map<String, List<String>>>{};
    for (final a in data.announcements) {
      if (cinema != null && a.cinema != cinema) continue;
      final dates = announced.putIfAbsent(a.filmId, () => {}).putIfAbsent(a.cinema, () => []);
      if (a.date != null) dates.add(a.date!);
    }
    return Programme._(data, now, day, upcoming, firstByCinema, byCinemaDay, announced);
  }

  bool hasShows(Film film) => _firstByCinema[film.id]?.isNotEmpty ?? false;

  /// Today's remaining shows, or the next day's: null when the film has no shows left.
  NextShows? nextShows(Film film) {
    final byDay = _upcoming[film.id];
    if (byDay == null || byDay.isEmpty) return null;
    final first = (byDay.keys.toList()..sort()).first;
    return NextShows(first, byDay[first]!);
  }

  /// The cinemas with shows or announcements of the film, the first date first.
  List<CinemaRelease> cinemaReleases(Film film) {
    final shows = _firstByCinema[film.id] ?? {};
    final list = [for (final e in shows.entries) CinemaRelease(e.key, e.value)];
    for (final e in (_announced[film.id] ?? <String, List<String>>{}).entries) {
      if (shows.containsKey(e.key)) continue;
      final dates = [...e.value]..sort();
      list.add(CinemaRelease(e.key, dates.isEmpty ? null : dates.first, announced: true));
    }
    list.sort((a, b) {
      if ((a.date == null) != (b.date == null)) return a.date == null ? 1 : -1;
      final byDate = (a.date ?? '').compareTo(b.date ?? '');
      return byDate != 0 ? byDate : a.cinema.compareTo(b.cinema);
    });
    return list;
  }

  /// Films in theaters with shows still to come (the "In sala" count of the menu).
  List<Film> get inSala => [for (final f in data.films) if (f.inSala && hasShows(f)) f];

  /// Films coming out that some cinema shows or announces (the "In uscita" count).
  List<Film> get inUscita => [for (final f in data.films) if (f.inUscita && cinemaReleases(f).isNotEmpty) f];
}

/// {sala: shows} -> salas sorted by first show, each with its shows in order and without repeats.
List<MapEntry<String, List<UpcomingShow>>> sortedSalas(Map<String, List<UpcomingShow>> bySala) {
  final salas = [
    for (final e in bySala.entries)
      MapEntry(e.key, {for (final s in e.value) s.start: s}.values.toList()..sort((a, b) => a.start.compareTo(b.start))),
  ];
  salas.sort((a, b) {
    final byStart = a.value.first.start.compareTo(b.value.first.start);
    return byStart != 0 ? byStart : a.key.compareTo(b.key);
  });
  return salas;
}
