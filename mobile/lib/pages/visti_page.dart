import 'package:flutter/material.dart';

import '../data/format.dart';
import '../data/letterboxd.dart';
import '../data/models.dart';
import '../data/personal.dart';
import '../data/repository.dart';
import '../data/schedule.dart';
import '../theme.dart';
import '../widgets/film_widgets.dart';
import '../widgets/letterboxd_widgets.dart';
import 'film_page.dart';

/// "Visti": films marked ✓, with day and cinema to correct, the statistics, and the file
/// for the Letterboxd diary.
class VistiPage extends StatelessWidget {
  const VistiPage({super.key, required this.store, this.scroll});

  final DataStore store;
  final ScrollController? scroll; // to go back to the top (tap on the open tab)

  @override
  Widget build(BuildContext context) {
    final data = store.data!;
    final personal = PersonalScope.of(context);
    final today = programmeDay(store.now);
    final films = seenFilms(data, personal);
    final ready = toDiary(data, personal);
    final missing = [for (final f in films) if (!personal.diary.containsKey(f.id) && f.tmdbId == null) f];

    return RefreshIndicator(
      onRefresh: store.refresh,
      child: ListView(
        controller: scroll,
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
        children: [
          const PageHeader(
              title: 'Visti',
              subtitle: 'Film segnati ✓: giorno e cinema si possono correggere qui. Da qui vanno nel diario di Letterboxd.'),
          if (ready.isNotEmpty)
            ExportBox(
              title: 'Da mettere nel diario',
              count: ready.length,
              steps: const [
                'Scarica il file CSV.',
                'Su Letterboxd: Impostazioni → Importa ed esporta → Importa i tuoi dati. '
                    'Ogni film diventa una voce del diario con la sua data.',
                'Torna qui e segnali come importati, così non finiscono nel prossimo file.',
              ],
              downloadLabel: 'Scarica CSV per il diario',
              onDownload: () =>
                  shareTextFile(context, 'letterboxd_diario_$today.csv', diaryCsv(ready, personal.seen), 'text/csv'),
              onImported: () async {
                if (await confirmImported(context)) await personal.markDiary([for (final f in ready) f.id], today);
              },
            ),
          if (missing.isNotEmpty) MissingTmdbNotice(films: missing),
          if (films.isEmpty)
            const EmptyState('Nessun film visto per ora.\nQuando vedi un film al cinema, segnalo con ✓.')
          else ...[
            SeenStatsView(stats: SeenStats.of(films, personal.seen, data, today)),
            const SizedBox(height: 18),
            const Text('Elenco', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            for (final f in films) _SeenRow(film: f, store: store, today: today),
          ],
        ],
      ),
    );
  }
}

/// A seen film: poster, title, day and cinema to correct, and where it stands with Letterboxd.
class _SeenRow extends StatelessWidget {
  const _SeenRow({required this.film, required this.store, required this.today});

  final Film film;
  final DataStore store;
  final String today;

  void _open(BuildContext context) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => FilmPage(film: film, store: store)));

  Future<void> _pickDate(BuildContext context, PersonalStore personal, String? current) async {
    final last = parseDay(today);
    final initial = current != null ? parseDay(current) : last;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial.isAfter(last) ? last : initial,
      firstDate: DateTime(2000),
      lastDate: last,
      helpText: "Quando l'hai visto?",
    );
    if (picked != null) await personal.setSeen(film.id, date: isoDate(picked));
  }

  @override
  Widget build(BuildContext context) {
    final data = store.data!;
    final personal = PersonalScope.of(context);
    final info = personal.seen[film.id];
    final inDiary = personal.diary.containsKey(film.id);
    // A cinema no longer followed still shows by its name in the menu
    final cinemas = {for (final c in data.cinemas) c.slug: c.name};
    if (info?.cinema case final c? when !cinemas.containsKey(c)) cinemas[c] = c;

    return Card(
      color: CnvColors.surface,
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GestureDetector(onTap: () => _open(context), child: Poster(url: film.poster, width: 52)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  InkWell(
                    onTap: () => _open(context),
                    child: Text(film.title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      OutlinedButton.icon(
                        style: OutlinedButton.styleFrom(
                            visualDensity: VisualDensity.compact, padding: const EdgeInsets.symmetric(horizontal: 10)),
                        onPressed: () => _pickDate(context, personal, info?.date),
                        icon: const Icon(Icons.calendar_today, size: 16),
                        label: Text(info?.date != null ? longDate(info!.date!, today) : 'Giorno?'),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: DropdownButton<String?>(
                          value: info?.cinema,
                          isExpanded: true,
                          isDense: true,
                          hint: const Text('Cinema?'),
                          underline: const SizedBox(),
                          items: [
                            const DropdownMenuItem<String?>(value: null, child: Text('Cinema?')),
                            for (final e in cinemas.entries)
                              DropdownMenuItem<String?>(value: e.key, child: Text(e.value, overflow: TextOverflow.ellipsis)),
                          ],
                          onChanged: (v) => personal.setSeen(film.id, cinema: v, clearCinema: v == null),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          inDiary
                              ? 'Nel diario di Letterboxd'
                              : film.tmdbId != null
                                  ? 'Da mettere nel diario'
                                  : 'Senza abbinamento TMDB',
                          style: const TextStyle(fontSize: 12, color: CnvColors.textMuted),
                        ),
                      ),
                      if (inDiary)
                        TextButton(
                          style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                          onPressed: () => personal.diaryAgain(film.id),
                          child: const Text('Esporta di nuovo'),
                        ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Statistiche": four numbers and bars by month, cinema and genre.
class SeenStatsView extends StatelessWidget {
  const SeenStatsView({super.key, required this.stats});

  final SeenStats stats;

  @override
  Widget build(BuildContext context) {
    final tiles = [
      _Tile('${stats.total}', 'film visti', big: true),
      _Tile('${stats.thisMonth}', 'questo mese', big: true),
      if (stats.topCinema != null) _Tile(stats.topCinema!, 'cinema più frequentato'),
      if (stats.topGenre != null) _Tile(stats.topGenre!, 'genere più visto'),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text('Statistiche', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        for (var i = 0; i < tiles.length; i += 2)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: tiles[i]),
                  const SizedBox(width: 8),
                  Expanded(child: i + 1 < tiles.length ? tiles[i + 1] : const SizedBox()),
                ],
              ),
            ),
          ),
        _Bars(title: 'Al mese', rows: stats.byMonth),
        _Bars(title: 'Per cinema', rows: stats.byCinema),
        _Bars(title: 'Per genere', rows: stats.byGenre),
      ],
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile(this.value, this.caption, {this.big = false});

  final String value;
  final String caption;
  final bool big;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: CnvColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CnvColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(value,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: big ? 24 : 15, fontWeight: FontWeight.w800, color: big ? CnvColors.accent : CnvColors.text)),
          Text(caption, style: const TextStyle(fontSize: 12, color: CnvColors.textMuted)),
        ],
      ),
    );
  }
}

class _Bars extends StatelessWidget {
  const _Bars({required this.title, required this.rows});

  final String title;
  final List<(String, int)> rows;

  @override
  Widget build(BuildContext context) {
    final max = rows.fold(1, (m, r) => r.$2 > m ? r.$2 : m);
    return Container(
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: CnvColors.surface, borderRadius: BorderRadius.circular(8)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          for (final (label, n) in rows)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                children: [
                  SizedBox(
                    width: 110,
                    child: Text(label, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12)),
                  ),
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: n / max,
                        minHeight: 8,
                        backgroundColor: CnvColors.surface2,
                        color: CnvColors.accent,
                      ),
                    ),
                  ),
                  SizedBox(
                    width: 28,
                    child: Text('$n', textAlign: TextAlign.right, style: const TextStyle(fontSize: 12)),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
