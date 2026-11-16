import 'package:flutter/material.dart';

import '../data/format.dart';
import '../data/models.dart';
import '../data/programme.dart';
import '../data/repository.dart';
import '../data/schedule.dart';
import '../theme.dart';
import '../widgets/film_widgets.dart';
import '../widgets/vote_buttons.dart';
import 'cinema_page.dart';

/// One film: poster, data, and every show still to come, day by day, split by cinema.
class FilmPage extends StatelessWidget {
  const FilmPage({super.key, required this.film, required this.store});

  final Film film;
  final DataStore store;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final data = store.data!;
        final current = data.filmsById[film.id] ?? film; // the fresh data after a refresh
        final programme = Programme.build(data, store.now);
        final today = programme.day;
        final cinemas = _cinemaDays(programme, current);
        final releases = programme.cinemaReleases(current);
        final elsewhere = [for (final r in releases) if (r.announced) r];
        return Scaffold(
          appBar: AppBar(title: Text(current.title, overflow: TextOverflow.ellipsis)),
          body: RefreshIndicator(
            onRefresh: store.refresh,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Poster(url: current.poster, width: 120),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(current.title, style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w800, height: 1.2)),
                          const SizedBox(height: 6),
                          FilmMeta(film: current),
                          const SizedBox(height: 6),
                          Text(statusLine(current, releases, today), style: const TextStyle(fontSize: 13, color: CnvColors.textMuted)),
                          if (current.tmdbId != null)
                            TextButton.icon(
                              style: TextButton.styleFrom(padding: EdgeInsets.zero, visualDensity: VisualDensity.compact),
                              onPressed: () => openLink(context, 'https://www.themoviedb.org/movie/${current.tmdbId}'),
                              icon: const Icon(Icons.open_in_new, size: 16),
                              label: const Text('Scheda su TMDB'),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                VoteButtons(film: current, data: data, today: today),
                const SizedBox(height: 18),
                if (cinemas.isEmpty)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 20),
                    child: Text(_noShows(current, data, today), textAlign: TextAlign.center, style: const TextStyle(color: CnvColors.textMuted)),
                  )
                else ...[
                  const Text('Spettacoli', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  const Text("Tocca un orario per aprire la pagina d'acquisto sul sito del cinema.",
                      style: TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                  const SizedBox(height: 8),
                  for (final c in cinemas)
                    Card(
                      color: CnvColors.surface,
                      margin: const EdgeInsets.only(bottom: 10),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            InkWell(
                              onTap: () => openCinema(context, c.cinema, store),
                              child: Text(data.cinemasBySlug[c.cinema]?.name ?? c.cinema,
                                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                            ),
                            for (final d in c.days)
                              Padding(
                                padding: const EdgeInsets.only(top: 8),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    SizedBox(
                                      width: 76,
                                      child: Padding(
                                        padding: const EdgeInsets.only(top: 12),
                                        child: Text(capitalize(formatDay(d.key, today)),
                                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                                      ),
                                    ),
                                    Expanded(child: SalaList(bySala: d.value)),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                ],
                if (elsewhere.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      'In arrivo anche: ${elsewhere.map((r) => '${data.cinemasBySlug[r.cinema]?.name ?? r.cinema}${r.date != null ? ' (dal ${longDate(r.date!, today)})' : ''}').join(', ')}',
                      style: const TextStyle(fontSize: 13, color: CnvColors.textMuted),
                    ),
                  ),
                if (_sitePages(data, current, releases) case final pages when pages.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  const Text('Sui siti dei cinema', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                  const Text('La scheda del film sul sito di ogni cinema che lo proietta o lo annuncia.',
                      style: TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final p in pages)
                        ActionChip(
                          avatar: const Icon(Icons.language, size: 18),
                          label: Text(data.cinemasBySlug[p.key]?.name ?? p.key),
                          tooltip: 'Scheda sul sito',
                          onPressed: () => openLink(context, p.value),
                        ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  /// Cinemas showing the film, the one with the earliest show first, each with its days.
  static List<({String cinema, List<MapEntry<String, Map<String, List<UpcomingShow>>>> days})> _cinemaDays(
      Programme programme, Film film) {
    final list = <({String cinema, List<MapEntry<String, Map<String, List<UpcomingShow>>>> days})>[];
    for (final c in programme.byCinemaDay.entries) {
      final days = [
        for (final d in (c.value.keys.toList()..sort()))
          if (c.value[d]!.containsKey(film.id)) MapEntry(d, c.value[d]![film.id]!),
      ];
      if (days.isNotEmpty) list.add((cinema: c.key, days: days));
    }
    DateTime first(List<MapEntry<String, Map<String, List<UpcomingShow>>>> days) =>
        sortedSalas(days.first.value).first.value.first.start;
    list.sort((a, b) => first(a.days).compareTo(first(b.days)));
    return list;
  }

  /// Under the title: since when it is in theaters, when it comes out, or when it left.
  static String statusLine(Film film, List<CinemaRelease> releases, String today) {
    if (film.inSala && film.since != null) return 'In sala dal ${longDate(film.since!, today)}';
    if (film.inUscita) {
      final first = releases.where((r) => r.date != null).map((r) => r.date!).firstOrNull;
      return first != null ? 'In uscita dal ${longDate(first, today)}' : 'In uscita, data da definire';
    }
    if (film.status == 'uscito' && film.left != null) return 'Uscito dalle sale il ${longDate(film.left!, today)}';
    if (film.status == 'uscito' && film.since == null) return 'Non è arrivato in sala';
    return '';
  }

  /// cinema -> the film's page on its site: the cinemas with the soonest date first, as above.
  static List<MapEntry<String, String>> _sitePages(CnvData data, Film film, List<CinemaRelease> releases) {
    final pages = data.sitePages[film.id] ?? const <String, String>{};
    final order = [for (final r in releases) r.cinema, for (final c in data.cinemas) c.slug];
    return [
      for (final slug in {...order, ...pages.keys})
        if (pages[slug] case final url?) MapEntry(slug, url),
    ];
  }

  static String _noShows(Film film, CnvData data, String today) {
    if (film.inSala && film.lastSeen != null) {
      final days = film.event ? data.settings.daysToUscitoEvento : data.settings.daysToUscito;
      return 'Nessuno spettacolo in programma.\nEsce dalle sale il ${longDate(addDays(film.lastSeen!, days), today)} se non ricompare.';
    }
    return 'Nessuno spettacolo in programma.';
  }
}
