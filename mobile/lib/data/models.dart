/// The data published every night by GitHub as data.json (app/export_static.py).
///
/// Dates are kept as "YYYY-MM-DD" strings, as in the file: they compare in the right
/// order and need no time zone. Fields missing from an older file get a safe default.
library;

class Cinema {
  const Cinema({required this.slug, required this.name, required this.url});

  final String slug;
  final String name;
  final String url;

  factory Cinema.fromJson(Map<String, dynamic> j) =>
      Cinema(slug: j['slug'] as String, name: j['name'] as String, url: (j['url'] as String?) ?? '');
}

class Film {
  const Film({
    required this.id,
    required this.title,
    required this.status,
    this.rawTitle,
    this.tmdbId,
    this.poster,
    this.year,
    this.genre,
    this.runtime,
    this.event = false,
    this.lastSeen,
    this.left,
    this.since,
  });

  final int id;
  final String title; // TMDB title when the match is sure, else the cinema's
  final String? rawTitle; // the cinema's title, when different (for the search)
  final String status; // "in_sala" | "in_uscita" | "uscito"
  final int? tmdbId;
  final String? poster;
  final int? year;
  final String? genre;
  final int? runtime; // minutes
  final bool event;
  final String? lastSeen;
  final String? left; // day it left theaters
  final String? since; // first day shown in the area

  bool get inSala => status == 'in_sala';
  bool get inUscita => status == 'in_uscita';

  factory Film.fromJson(Map<String, dynamic> j) => Film(
        id: j['id'] as int,
        title: j['title'] as String,
        rawTitle: j['raw'] as String?,
        status: j['status'] as String,
        tmdbId: j['tmdb'] as int?,
        poster: j['poster'] as String?,
        year: j['year'] as int?,
        genre: j['genre'] as String?,
        runtime: j['runtime'] as int?,
        event: (j['event'] as bool?) ?? false,
        lastSeen: j['last_seen'] as String?,
        left: j['left'] as String?,
        since: j['since'] as String?,
      );
}

/// One screening, as listed by a cinema's site.
class Show {
  const Show({required this.filmId, required this.cinema, required this.day, required this.time, this.sala = '', this.url = ''});

  final int filmId;
  final String cinema; // cinema slug
  final String day; // programme day: shows before 06:00 run the night after
  final String time; // "HH:MM"
  final String sala;
  final String url; // the purchase page, else the film's page on the cinema site

  factory Show.fromJson(Map<String, dynamic> j) => Show(
        filmId: j['f'] as int,
        cinema: j['c'] as String,
        day: j['d'] as String,
        time: j['t'] as String,
        sala: (j['s'] as String?) ?? '',
        url: (j['u'] as String?) ?? '',
      );
}

/// A film announced by a cinema ("prossimamente"), maybe with a date.
class Announcement {
  const Announcement({required this.filmId, required this.cinema, this.date});

  final int filmId;
  final String cinema;
  final String? date;

  factory Announcement.fromJson(Map<String, dynamic> j) =>
      Announcement(filmId: j['f'] as int, cinema: j['c'] as String, date: j['d'] as String?);
}

class DataSettings {
  const DataSettings({this.daysToUscito = 7, this.daysToUscitoEvento = 3, this.showExtraMinutes = 10});

  final int daysToUscito;
  final int daysToUscitoEvento;
  final int showExtraMinutes; // ads and trailers before the film

  factory DataSettings.fromJson(Map<String, dynamic>? j) => DataSettings(
        daysToUscito: (j?['days_to_uscito'] as int?) ?? 7,
        daysToUscitoEvento: (j?['days_to_uscito_evento'] as int?) ?? 3,
        showExtraMinutes: (j?['show_extra_minutes'] as int?) ?? 10,
      );
}

class CnvData {
  CnvData({
    required this.generatedAt,
    required this.settings,
    required this.cinemas,
    required this.films,
    required this.shows,
    required this.announcements,
    this.merged = const {},
    this.notUpdated = const {},
  })  : filmsById = {for (final f in films) f.id: f},
        cinemasBySlug = {for (final c in cinemas) c.slug: c};

  final DateTime generatedAt;
  final DataSettings settings;
  final List<Cinema> cinemas;
  final List<Film> films;
  final List<Show> shows;
  final List<Announcement> announcements;
  final Map<int, int> merged; // duplicate merged by the sync -> the film that absorbed it
  final Map<String, String?> notUpdated; // cinema whose site did not answer -> last good day
  final Map<int, Film> filmsById;
  final Map<String, Cinema> cinemasBySlug;

  factory CnvData.fromJson(Map<String, dynamic> j) => CnvData(
        generatedAt: DateTime.parse(j['generated_at'] as String),
        settings: DataSettings.fromJson(j['settings'] as Map<String, dynamic>?),
        cinemas: [for (final c in (j['cinemas'] as List? ?? [])) Cinema.fromJson(c as Map<String, dynamic>)],
        films: [for (final f in (j['films'] as List? ?? [])) Film.fromJson(f as Map<String, dynamic>)],
        shows: [for (final s in (j['shows'] as List? ?? [])) Show.fromJson(s as Map<String, dynamic>)],
        announcements: [for (final c in (j['coming'] as List? ?? [])) Announcement.fromJson(c as Map<String, dynamic>)],
        merged: {
          for (final e in ((j['merged'] as Map<String, dynamic>?) ?? {}).entries) int.parse(e.key): e.value as int,
        },
        notUpdated: {
          for (final e in ((j['not_updated'] as Map<String, dynamic>?) ?? {}).entries) e.key: e.value as String?,
        },
      );
}
