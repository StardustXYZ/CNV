import 'package:flutter/material.dart';

import '../data/format.dart';
import '../data/models.dart';
import '../data/programme.dart';
import '../data/repository.dart';
import '../data/schedule.dart';
import '../theme.dart';
import '../widgets/film_widgets.dart';
import 'cinema_page.dart';
import 'film_page.dart';
import 'in_sala_page.dart' show titleMatches;

/// A film coming out, with its cinemas and its first known date (null: not announced yet).
class ComingFilm {
  const ComingFilm(this.film, this.releases, this.first);

  final Film film;
  final List<CinemaRelease> releases;
  final String? first;
}

/// The films coming out that a cinema shows or announces, the soonest first, undated last.
List<ComingFilm> comingFilms(Programme programme, String query) {
  final list = [
    for (final f in programme.data.films)
      if (f.inUscita && titleMatches(f, query))
        if (programme.cinemaReleases(f) case final releases when releases.isNotEmpty)
          ComingFilm(f, releases, releases.where((r) => r.date != null).map((r) => r.date!).firstOrNull),
  ];
  list.sort((a, b) {
    if ((a.first == null) != (b.first == null)) return a.first == null ? 1 : -1;
    final byDate = (a.first ?? '').compareTo(b.first ?? '');
    return byDate != 0 ? byDate : a.film.title.compareTo(b.film.title);
  });
  return list;
}

void _openFilm(BuildContext context, Film film, DataStore store) =>
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => FilmPage(film: film, store: store)));

/// "In uscita": the announced films, as a list grouped by date or as a month calendar.
class InUscitaPage extends StatefulWidget {
  const InUscitaPage({super.key, required this.store});

  final DataStore store;

  @override
  State<InUscitaPage> createState() => _InUscitaPageState();
}

class _InUscitaPageState extends State<InUscitaPage> {
  final _search = TextEditingController();
  bool _calendar = false;
  int _monthShift = 0; // months after the current one shown in the calendar

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final programme = Programme.build(widget.store.data!, widget.store.now);
    final films = comingFilms(programme, _search.text);
    return RefreshIndicator(
      onRefresh: widget.store.refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
        children: [
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('Elenco'), icon: Icon(Icons.view_list)),
              ButtonSegment(value: true, label: Text('Calendario'), icon: Icon(Icons.calendar_month)),
            ],
            selected: {_calendar},
            showSelectedIcon: false,
            onSelectionChanged: (s) => setState(() => _calendar = s.first),
          ),
          const SizedBox(height: 10),
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
          const SizedBox(height: 12),
          if (films.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 40),
              child: Text(_search.text.trim().isEmpty ? 'Nessun film in uscita al momento.' : 'Nessun film in uscita con questo titolo.',
                  textAlign: TextAlign.center, style: const TextStyle(color: CnvColors.textMuted)),
            )
          else if (_calendar)
            _MonthCalendar(
              films: films,
              today: programme.day,
              shift: _monthShift,
              onShift: (delta) => setState(() => _monthShift += delta),
              store: widget.store,
            )
          else
            ..._list(context, films, programme.day),
        ],
      ),
    );
  }

  List<Widget> _list(BuildContext context, List<ComingFilm> films, String today) {
    final widgets = <Widget>[];
    String? lastHeader;
    for (final c in films) {
      final header = c.first == null ? 'Data da definire' : 'Dal ${longDate(c.first!, today)}';
      if (header != lastHeader) {
        widgets.add(Padding(
          padding: const EdgeInsets.fromLTRB(2, 6, 0, 6),
          child: Text(header,
              style: TextStyle(fontWeight: FontWeight.w700, color: c.first == null ? CnvColors.textMuted : CnvColors.accent)),
        ));
        lastHeader = header;
      }
      widgets.add(_ComingCard(coming: c, today: today, store: widget.store));
    }
    return widgets;
  }
}

class _ComingCard extends StatelessWidget {
  const _ComingCard({required this.coming, required this.today, required this.store});

  final ComingFilm coming;
  final String today;
  final DataStore store;

  @override
  Widget build(BuildContext context) {
    final film = coming.film;
    return Card(
      color: CnvColors.surface,
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            GestureDetector(onTap: () => _openFilm(context, film, store), child: Poster(url: film.poster, width: 64)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  InkWell(
                    onTap: () => _openFilm(context, film, store),
                    child: Text(film.title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                  ),
                  const SizedBox(height: 3),
                  FilmMeta(film: film),
                  const SizedBox(height: 6),
                  for (final r in coming.releases)
                    Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: Wrap(
                        spacing: 6,
                        children: [
                          InkWell(
                            onTap: () => openCinema(context, r.cinema, store),
                            child: Text(store.data!.cinemasBySlug[r.cinema]?.name ?? r.cinema,
                                style: const TextStyle(fontSize: 13, color: CnvColors.accent)),
                          ),
                          if (r.date == null)
                            const Text('data da definire', style: TextStyle(fontSize: 12, color: CnvColors.textMuted))
                          else if (r.date != coming.first)
                            Text('dal ${longDate(r.date!, today)}', style: const TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                        ],
                      ),
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

const _calendarDays = ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom'];
const _monthNames = [
  'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
];

/// The month calendar: Monday to Sunday, each film on its first date; undated films below.
class _MonthCalendar extends StatelessWidget {
  const _MonthCalendar({required this.films, required this.today, required this.shift, required this.onShift, required this.store});

  final List<ComingFilm> films;
  final String today;
  final int shift;
  final ValueChanged<int> onShift;
  final DataStore store;

  @override
  Widget build(BuildContext context) {
    final todayDate = parseDay(today);
    final month = DateTime(todayDate.year, todayDate.month + shift);
    final monthKey = isoDate(month).substring(0, 7);
    final lastRelease = films.map((c) => c.first).whereType<String>().fold<String>(today, (a, b) => b.compareTo(a) > 0 ? b : a);
    final nextKey = isoDate(DateTime(month.year, month.month + 1)).substring(0, 7);
    final byDay = <String, List<Film>>{};
    for (final c in films) {
      if (c.first != null) byDay.putIfAbsent(c.first!, () => []).add(c.film);
    }
    // From the Monday on or before the 1st to the Sunday on or after the last day
    final start = DateTime(month.year, month.month, 1 - (month.weekday - 1));
    final end = DateTime(month.year, month.month + 1, 0);
    final days = <DateTime>[];
    for (var d = start; !d.isAfter(end) || days.length % 7 != 0; d = DateTime(d.year, d.month, d.day + 1)) {
      days.add(d);
    }
    final undated = [for (final c in films) if (c.first == null) c.film];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            IconButton(
              tooltip: 'Mese precedente',
              onPressed: shift > 0 ? () => onShift(-1) : null,
              icon: const Icon(Icons.chevron_left),
            ),
            Expanded(
              child: Text('${_monthNames[month.month - 1]} ${month.year}',
                  textAlign: TextAlign.center, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
            ),
            IconButton(
              tooltip: 'Mese successivo',
              onPressed: nextKey.compareTo(lastRelease.substring(0, 7)) <= 0 ? () => onShift(1) : null,
              icon: const Icon(Icons.chevron_right),
            ),
          ],
        ),
        Row(
          children: [
            for (final name in _calendarDays)
              Expanded(
                child: Text(name.toUpperCase(),
                    textAlign: TextAlign.center, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: CnvColors.textMuted)),
              ),
          ],
        ),
        const SizedBox(height: 4),
        for (var week = 0; week < days.length; week += 7)
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final d in days.sublist(week, week + 7))
                  Expanded(child: _DayCell(day: d, inMonth: isoDate(d).startsWith(monthKey), today: today, films: byDay[isoDate(d)] ?? const [], store: store)),
              ],
            ),
          ),
        if (undated.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('Data da definire', style: TextStyle(fontWeight: FontWeight.w700, color: CnvColors.textMuted)),
          for (final f in undated)
            ListTile(dense: true, contentPadding: EdgeInsets.zero, title: Text(f.title), onTap: () => _openFilm(context, f, store)),
        ],
      ],
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({required this.day, required this.inMonth, required this.today, required this.films, required this.store});

  final DateTime day;
  final bool inMonth;
  final String today;
  final List<Film> films;
  final DataStore store;

  @override
  Widget build(BuildContext context) {
    final iso = isoDate(day);
    final isToday = iso == today;
    return Opacity(
      opacity: inMonth ? 1 : 0.35,
      child: Container(
        margin: const EdgeInsets.all(1.5),
        padding: const EdgeInsets.all(3),
        constraints: const BoxConstraints(minHeight: 54),
        decoration: BoxDecoration(
          color: CnvColors.surface,
          borderRadius: BorderRadius.circular(6),
          border: isToday ? Border.all(color: CnvColors.accent, width: 1.5) : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${day.day}',
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: iso.compareTo(today) < 0 ? CnvColors.textMuted : CnvColors.text)),
            for (final f in films)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Tooltip(
                  message: f.title,
                  child: GestureDetector(
                    onTap: () => _openFilm(context, f, store),
                    child: Poster(url: f.poster),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
