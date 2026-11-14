import 'dart:async';

import 'package:flutter/material.dart';

import '../data/format.dart';
import '../data/models.dart';
import '../data/personal.dart';
import '../data/programme.dart';
import '../data/repository.dart';
import '../data/schedule.dart';
import '../theme.dart';
import '../widgets/film_widgets.dart';
import '../widgets/vote_buttons.dart';
import 'cinema_page.dart';
import 'film_page.dart';

/// Words of a title without accents, case and punctuation: "Città" is found by "citta".
String normalizeTitle(String text) {
  const accents = {'à': 'a', 'á': 'a', 'è': 'e', 'é': 'e', 'ì': 'i', 'í': 'i', 'ò': 'o', 'ó': 'o', 'ù': 'u', 'ú': 'u'};
  final lower = text.toLowerCase().split('').map((c) => accents[c] ?? c).join();
  return lower.replaceAll(RegExp(r'[^a-z0-9\s]'), '').replaceAll(RegExp(r'\s+'), ' ').trim();
}

bool titleMatches(Film film, String query) {
  final q = normalizeTitle(query);
  if (q.isEmpty) return true;
  return [film.title, film.rawTitle].any((t) => t != null && normalizeTitle(t).contains(q));
}

/// "In sala": the films programmed now, the latest arrivals first, with today's shows (or
/// the next day's), filters by title, genre and cinema, and the films no longer programmed.
class InSalaPage extends StatefulWidget {
  const InSalaPage({super.key, required this.store});

  final DataStore store;

  @override
  State<InSalaPage> createState() => _InSalaPageState();
}

class _InSalaPageState extends State<InSalaPage> {
  final _search = TextEditingController();
  String? _genre;
  String? _cinema;
  String? _vote; // null: all; '': not voted yet; 'V' / '?'
  Timer? _minute;

  @override
  void initState() {
    super.initState();
    // Shows that start disappear while the app stays open
    _minute = Timer.periodic(const Duration(minutes: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _minute?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _clearFilters() => setState(() {
        _search.clear();
        _genre = null;
        _cinema = null;
        _vote = null;
      });

  bool _voteMatches(String? vote) => _vote == null || (_vote!.isEmpty ? vote == null : vote == _vote);

  @override
  Widget build(BuildContext context) {
    final data = widget.store.data!;
    final personal = PersonalScope.of(context);
    final now = widget.store.now;
    final all = Programme.build(data, now);
    final programme = _cinema == null ? all : Programme.build(data, now, cinema: _cinema);
    final inSala = [for (final f in data.films) if (f.inSala) f];
    final genres = {for (final f in inSala) ?f.genre}.toList()..sort();
    if (!genres.contains(_genre)) _genre = null;

    final films = [
      for (final f in inSala)
        if ((_genre == null || f.genre == _genre) && _voteMatches(personal.vote(f.id)) && titleMatches(f, _search.text)) f,
    ];
    final showing = [for (final f in films) if (programme.hasShows(f)) f]
      ..sort((a, b) {
        final bySince = (b.since ?? '').compareTo(a.since ?? ''); // latest arrivals first
        return bySince != 0 ? bySince : a.title.compareTo(b.title);
      });
    // With a cinema chosen, films not on there are simply left out
    final gone = _cinema != null ? <Film>[] : ([for (final f in films) if (!all.hasShows(f)) f]..sort((a, b) => a.title.compareTo(b.title)));
    final filtered = _search.text.trim().isNotEmpty || _genre != null || _cinema != null || _vote != null;

    return RefreshIndicator(
      onRefresh: widget.store.refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
        children: [
          NotUpdatedNotice(data: data, cinema: _cinema),
          TextField(
            controller: _search,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              hintText: 'Cerca un titolo',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _search.text.isEmpty
                  ? null
                  : IconButton(icon: const Icon(Icons.close), onPressed: () => setState(_search.clear)),
              isDense: true,
              filled: true,
              fillColor: CnvColors.surface,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _FilterMenu(
                  value: _genre,
                  all: 'Tutti i generi',
                  options: {for (final g in genres) g: g},
                  onChanged: (v) => setState(() => _genre = v),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _FilterMenu(
                  value: _cinema,
                  all: 'Tutti i cinema',
                  options: {for (final c in data.cinemas) c.slug: c.name},
                  onChanged: (v) => setState(() => _cinema = v),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            children: [
              for (final (value, label) in const [(null, 'Tutti'), ('', 'Da votare'), ('V', 'V'), ('?', '?')])
                ChoiceChip(
                  label: Text(label),
                  selected: _vote == value,
                  showCheckmark: false,
                  visualDensity: VisualDensity.compact,
                  onSelected: (_) => setState(() => _vote = value),
                ),
            ],
          ),
          if (filtered)
            Row(
              children: [
                Text('${showing.length} film', style: const TextStyle(color: CnvColors.textMuted)),
                TextButton(onPressed: _clearFilters, child: const Text('Togli filtri')),
              ],
            ),
          const SizedBox(height: 8),
          if (showing.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 40),
              child: Text(filtered ? 'Nessun film in sala con questi filtri.' : 'Nessun film in programmazione.',
                  textAlign: TextAlign.center, style: const TextStyle(color: CnvColors.textMuted)),
            ),
          for (final f in showing) FilmCard(film: f, programme: programme, store: widget.store),
          if (gone.isNotEmpty) _GoneSection(films: gone, data: data, today: programme.day, store: widget.store),
        ],
      ),
    );
  }
}

class _FilterMenu extends StatelessWidget {
  const _FilterMenu({required this.value, required this.all, required this.options, required this.onChanged});

  final String? value;
  final String all;
  final Map<String, String> options; // value -> label
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String?>(
      initialValue: value,
      isExpanded: true,
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: CnvColors.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
      ),
      items: [
        DropdownMenuItem<String?>(value: null, child: Text(all, overflow: TextOverflow.ellipsis)),
        for (final e in options.entries)
          DropdownMenuItem<String?>(value: e.key, child: Text(e.value, overflow: TextOverflow.ellipsis)),
      ],
      onChanged: onChanged,
    );
  }
}

/// A film in "In sala": poster, title, data, and its next shows by cinema and sala.
class FilmCard extends StatelessWidget {
  const FilmCard({super.key, required this.film, required this.programme, required this.store});

  final Film film;
  final Programme programme;
  final DataStore store;

  void _open(BuildContext context) =>
      Navigator.of(context).push(MaterialPageRoute(builder: (_) => FilmPage(film: film, store: store)));

  @override
  Widget build(BuildContext context) {
    final next = programme.nextShows(film);
    // The cinema with the earliest show first
    DateTime firstStart(Map<String, List<UpcomingShow>> bySala) => sortedSalas(bySala).first.value.first.start;
    final cinemas = (next?.byCinema.entries.toList() ?? <MapEntry<String, Map<String, List<UpcomingShow>>>>[])
      ..sort((a, b) => firstStart(a.value).compareTo(firstStart(b.value)));
    final elsewhere = [for (final r in programme.cinemaReleases(film)) if (r.announced) r];
    return Card(
      color: CnvColors.surface,
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GestureDetector(onTap: () => _open(context), child: Poster(url: film.poster, width: 78)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  InkWell(
                    onTap: () => _open(context),
                    child: Text(film.title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                  ),
                  const SizedBox(height: 3),
                  FilmMeta(film: film),
                  if (film.since != null)
                    Text('In sala dal ${longDate(film.since!, programme.day)}',
                        style: const TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                  if (next != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      next.day == programme.day ? 'OGGI' : 'PROSSIMI SPETTACOLI: ${formatDay(next.day, programme.day).toUpperCase()}',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.6,
                        color: next.day == programme.day ? CnvColors.textMuted : CnvColors.accent,
                      ),
                    ),
                    for (final c in cinemas) ...[
                      const SizedBox(height: 6),
                      InkWell(
                        onTap: () => openCinema(context, c.key, store),
                        child: Text(store.data!.cinemasBySlug[c.key]?.name ?? c.key,
                            style: const TextStyle(fontSize: 13, color: CnvColors.accent, fontWeight: FontWeight.w600)),
                      ),
                      SalaList(bySala: c.value),
                    ],
                  ],
                  if (elsewhere.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        'In arrivo anche: ${elsewhere.map((r) => '${store.data!.cinemasBySlug[r.cinema]?.name ?? r.cinema}${r.date != null ? ' (dal ${longDate(r.date!, programme.day)})' : ''}').join(', ')}',
                        style: const TextStyle(fontSize: 12, color: CnvColors.textMuted),
                      ),
                    ),
                  const SizedBox(height: 10),
                  VoteButtons(film: film, data: store.data!, today: programme.day),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Non più in programmazione": gone from the cinemas' sites, waiting to become "uscito".
class _GoneSection extends StatelessWidget {
  const _GoneSection({required this.films, required this.data, required this.today, required this.store});

  final List<Film> films;
  final CnvData data;
  final String today;
  final DataStore store;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: CnvColors.surface,
      margin: const EdgeInsets.only(top: 6),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          title: Text('Non più in programmazione (${films.length})', style: const TextStyle(fontSize: 15)),
          subtitle: const Text('Spariti dai siti dei cinema, in attesa di essere segnati come usciti',
              style: TextStyle(fontSize: 12, color: CnvColors.textMuted)),
          children: [
            for (final f in films)
              ListTile(
                dense: true,
                title: Text(f.title),
                subtitle: Text(_exitText(f), style: const TextStyle(color: CnvColors.textMuted)),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => FilmPage(film: f, store: store))),
              ),
          ],
        ),
      ),
    );
  }

  String _exitText(Film f) {
    if (f.lastSeen == null) return '';
    final days = f.event ? data.settings.daysToUscitoEvento : data.settings.daysToUscito;
    return "Visto l'ultima volta ${formatDay(f.lastSeen!, today)} · uscito dalle sale dal "
        '${longDate(addDays(f.lastSeen!, days), today)} se non ricompare';
  }
}
