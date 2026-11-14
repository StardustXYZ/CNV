import 'package:flutter/material.dart';

import '../data/format.dart';
import '../data/letterboxd.dart';
import '../data/personal.dart';
import '../data/repository.dart';
import '../data/schedule.dart';
import '../theme.dart';
import '../widgets/film_widgets.dart';
import '../widgets/letterboxd_widgets.dart';
import '../widgets/vote_buttons.dart';
import 'film_page.dart';

/// "Watchlist": films marked V or ? that left the cinemas, to add to the watchlist on Letterboxd.
class WatchlistPage extends StatelessWidget {
  const WatchlistPage({super.key, required this.store});

  final DataStore store;

  @override
  Widget build(BuildContext context) {
    final data = store.data!;
    final personal = PersonalScope.of(context);
    final today = programmeDay(store.now);
    final watch = watchlistFilms(data, personal);
    final ready = toExport(data, personal);
    final missing = [for (final f in watch) if (!personal.exported.containsKey(f.id) && f.tmdbId == null) f];
    final done = [for (final f in watch) if (personal.exported.containsKey(f.id)) f]
      ..sort((a, b) => personal.exported[b.id]!.compareTo(personal.exported[a.id]!));

    return RefreshIndicator(
      onRefresh: store.refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
        children: [
          const PageHeader(
              title: 'Watchlist',
              subtitle: 'Film usciti dalle sale che avevi segnato V o ?, da aggiungere alla watchlist di Letterboxd.'),
          if (ready.isNotEmpty) ...[
            ExportBox(
              title: 'Da esportare',
              count: ready.length,
              steps: const [
                'Scarica il file CSV.',
                'Importalo nella tua watchlist su Letterboxd (importazione da CSV).',
                'Torna qui e segna i film come esportati, così non finiscono nel prossimo file.',
              ],
              downloadLabel: 'Scarica CSV per Letterboxd',
              onDownload: () => shareTextFile(context, 'letterboxd_watchlist_$today.csv', watchlistCsv(ready), 'text/csv'),
              onImported: () async {
                if (await confirmImported(context)) await personal.markExported([for (final f in ready) f.id], today);
              },
            ),
            for (final f in ready)
              Card(
                color: CnvColors.surface,
                margin: const EdgeInsets.only(bottom: 10),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GestureDetector(onTap: () => _open(context, f.id), child: Poster(url: f.poster, width: 58)),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            InkWell(
                              onTap: () => _open(context, f.id),
                              child: Text(f.year != null ? '${f.title} (${f.year})' : f.title,
                                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                            ),
                            const SizedBox(height: 2),
                            FilmMeta(film: f),
                            if (f.left != null)
                              Text('Uscito dalle sale il ${longDate(f.left!, today)}',
                                  style: const TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                            const SizedBox(height: 8),
                            VoteButtons(film: f, data: data, today: today),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
          if (missing.isNotEmpty) MissingTmdbNotice(films: missing),
          if (ready.isEmpty && missing.isEmpty)
            const EmptyState('Nessun film da esportare per ora.\n'
                'Quando un film segnato V o ? esce da tutte le sale, apparirà qui.'),
          if (done.isNotEmpty)
            Card(
              color: CnvColors.surface,
              margin: const EdgeInsets.only(top: 6),
              child: Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  title: Text('Già esportati (${done.length})', style: const TextStyle(fontSize: 15)),
                  children: [
                    for (final f in done)
                      ListTile(
                        dense: true,
                        title: Text(f.year != null ? '${f.title} (${f.year})' : f.title),
                        subtitle: Text('esportato ${formatDay(personal.exported[f.id]!, today)}',
                            style: const TextStyle(color: CnvColors.textMuted)),
                        trailing: TextButton(
                          onPressed: () => personal.exportAgain(f.id),
                          child: const Text('Esporta di nuovo'),
                        ),
                        onTap: () => _open(context, f.id),
                      ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  void _open(BuildContext context, int id) => Navigator.of(context)
      .push(MaterialPageRoute(builder: (_) => FilmPage(film: store.data!.filmsById[id]!, store: store)));
}
