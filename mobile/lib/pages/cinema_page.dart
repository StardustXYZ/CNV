import 'dart:async';

import 'package:flutter/material.dart';

import '../data/format.dart';
import '../data/programme.dart';
import '../data/repository.dart';
import '../theme.dart';
import '../widgets/bottom_padding.dart';
import '../widgets/film_widgets.dart';
import '../widgets/vote_buttons.dart';
import 'film_page.dart';
import 'in_uscita_page.dart' show ComingCard, comingFilms;

/// Opens a cinema's page (from the menu or by touching its name).
void openCinema(BuildContext context, String slug, DataStore store) =>
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => CinemaPage(slug: slug, store: store)));

/// One cinema: the days its site lists, and the films of the chosen day with their shows.
class CinemaPage extends StatefulWidget {
  const CinemaPage({super.key, required this.slug, required this.store});

  final String slug;
  final DataStore store;

  @override
  State<CinemaPage> createState() => _CinemaPageState();
}

class _CinemaPageState extends State<CinemaPage> {
  String? _chosen; // day picked in the calendar; null = the first one with shows
  Timer? _minute;
  final _dayKeys = <String, GlobalKey>{}; // one per day chip, to scroll the chosen one into view

  /// A day chip was tapped: choose the day and bring its chip fully into view.
  void _showDay(String day) {
    setState(() => _chosen = day);
    final chip = _dayKeys[day]?.currentContext;
    if (chip == null) return;
    Scrollable.ensureVisible(chip, alignment: 0.5, duration: const Duration(milliseconds: 200), curve: Curves.easeInOut);
  }

  @override
  void initState() {
    super.initState();
    _minute = Timer.periodic(const Duration(minutes: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _minute?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.store,
      builder: (context, _) {
        final data = widget.store.data!;
        final cinema = data.cinemasBySlug[widget.slug];
        final programme = Programme.build(data, widget.store.now, cinema: widget.slug);
        final byDay = programme.byCinemaDay[widget.slug] ?? {};
        final days = byDay.keys.toList()..sort();
        final selected = days.contains(_chosen) ? _chosen! : (days.isEmpty ? null : days.first);
        // Opened without choosing a day and nothing left today: say these are a later day's
        final todayOver = _chosen == null && selected != null && selected != programme.day;
        final films = selected == null ? <MapEntry<int, Map<String, List<UpcomingShow>>>>[] : byDay[selected]!.entries.toList();
        DateTime firstStart(Map<String, List<UpcomingShow>> bySala) => sortedSalas(bySala).first.value.first.start;
        films.sort((a, b) => firstStart(a.value).compareTo(firstStart(b.value)));
        final coming = comingFilms(programme, ''); // only this cinema's shows and announcements

        return Title(
          title: '${cinema?.name ?? widget.slug} · CNV',
          color: CnvColors.background,
          child: Scaffold(
            appBar: AppBar(
              title: Text(cinema?.name ?? widget.slug, overflow: TextOverflow.ellipsis),
              actions: [
                if (cinema != null && cinema.url.isNotEmpty)
                  IconButton(
                    tooltip: 'Sito del cinema',
                    icon: const Icon(Icons.open_in_new),
                    onPressed: () => openLink(context, cinema.url),
                  ),
              ],
            ),
            body: RefreshIndicator(
              onRefresh: widget.store.refresh,
              child: ListView(
                padding: EdgeInsets.fromLTRB(12, 12, 12, BottomPadding.of(context, minimum: 24)),
                children: [
                  NotUpdatedNotice(data: data, cinema: widget.slug),
                  if (days.isEmpty) ...[
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 30),
                      child: Text('Il sito del cinema non ha spettacoli in programma.',
                          textAlign: TextAlign.center, style: TextStyle(color: CnvColors.textMuted)),
                    ),
                    if (cinema != null && cinema.url.isNotEmpty)
                      Center(
                        child: OutlinedButton.icon(
                          onPressed: () => openLink(context, cinema.url),
                          icon: const Icon(Icons.open_in_new, size: 18),
                          label: const Text('Controlla sul sito del cinema'),
                        ),
                      ),
                  ] else ...[
                    SizedBox(
                      height: 40,
                      // Wider than the page by its 12px padding on each side: the chips slide to the screen edge
                      child: LayoutBuilder(
                        builder: (context, box) => OverflowBox(
                          minWidth: box.maxWidth + 24,
                          maxWidth: box.maxWidth + 24,
                          child: ShaderMask(
                            // the end edge fades: there is more to scroll
                            shaderCallback: (Rect bounds) => const LinearGradient(
                              begin: Alignment.centerLeft,
                              end: Alignment.centerRight,
                              colors: [Colors.white, Colors.white, Colors.white, Colors.transparent],
                              stops: [0.0, 0.0, 0.88, 1.0],
                            ).createShader(bounds),
                            blendMode: BlendMode.dstIn,
                            child: ListView(
                              scrollDirection: Axis.horizontal,
                              padding: const EdgeInsets.symmetric(horizontal: 12),
                              children: [
                                for (final d in days)
                                  Padding(
                                    key: _dayKeys.putIfAbsent(d, GlobalKey.new),
                                    padding: const EdgeInsets.only(right: 6),
                                    child: ChoiceChip(
                                      label: Text(d == programme.day ? 'Oggi' : capitalize(formatDay(d, programme.day))),
                                      selected: d == selected,
                                      showCheckmark: false,
                                      onSelected: (_) => _showDay(d),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    const Text("Tocca un orario per aprire la pagina d'acquisto sul sito del cinema.",
                        style: TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                    if (todayOver)
                      Container(
                        margin: const EdgeInsets.only(top: 10),
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: CnvColors.surface,
                          borderRadius: BorderRadius.circular(8),
                          border: const Border(left: BorderSide(color: CnvColors.yellow, width: 3)),
                        ),
                        child: Text('Oggi non ci sono altri spettacoli: ecco quelli di ${formatDay(selected, programme.day)}.',
                            style: const TextStyle(fontSize: 13)),
                      ),
                    const SizedBox(height: 10),
                    for (final f in films)
                      if (data.filmsById[f.key] case final film?)
                        Card(
                          color: CnvColors.surface,
                          margin: const EdgeInsets.only(bottom: 10),
                          child: Padding(
                            padding: const EdgeInsets.all(10),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                GestureDetector(
                                  onTap: () => _openFilm(context, film.id),
                                  child: Poster(url: film.poster, width: 58),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      InkWell(
                                        onTap: () => _openFilm(context, film.id),
                                        child: Text(film.title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                                      ),
                                      const SizedBox(height: 2),
                                      FilmMeta(film: film),
                                      SalaList(bySala: f.value),
                                      const SizedBox(height: 8),
                                      VoteButtons(film: film, data: data, today: programme.day),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                  ],
                  if (coming.isNotEmpty) ...[
                    const SizedBox(height: 14),
                    const Text('In arrivo qui', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    const Text('I film che questo cinema proietterà o annuncia.',
                        style: TextStyle(fontSize: 12, color: CnvColors.textMuted)),
                    const SizedBox(height: 8),
                    for (final c in coming)
                      ComingCard(coming: c, today: programme.day, store: widget.store, showCinemas: false),
                  ],
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  void _openFilm(BuildContext context, int id) {
    final film = widget.store.data!.filmsById[id]!;
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => FilmPage(film: film, store: widget.store)));
  }
}

/// The side menu: every cinema, with how many films it still shows today.
class CinemaDrawer extends StatelessWidget {
  const CinemaDrawer({super.key, required this.store});

  final DataStore store;

  @override
  Widget build(BuildContext context) {
    final data = store.data;
    final programme = data == null ? null : Programme.build(data, store.now);
    return Drawer(
      backgroundColor: CnvColors.surface,
      child: SafeArea(
        bottom: false,
        child: ListView(
          padding: EdgeInsets.only(bottom: BottomPadding.of(context)),
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Text('Cinema', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
            ),
            if (data == null)
              const ListTile(title: Text('Nessun dato', style: TextStyle(color: CnvColors.textMuted))),
            if (data != null)
              for (final c in data.cinemas)
                ListTile(
                  title: Text(c.name),
                  contentPadding: const EdgeInsets.only(left: 16, right: 4),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      ?_todayCount(programme!, c.slug),
                      if (c.url.isNotEmpty)
                        IconButton(
                          tooltip: 'Sito di ${c.name}',
                          icon: const Icon(Icons.language, color: CnvColors.textMuted),
                          onPressed: () => openLink(context, c.url),
                        ),
                    ],
                  ),
                  onTap: () {
                    Navigator.of(context).pop(); // close the menu
                    openCinema(context, c.slug, store);
                  },
                ),
          ],
        ),
      ),
    );
  }

  Widget? _todayCount(Programme programme, String slug) {
    final n = programme.byCinemaDay[slug]?[programme.day]?.length ?? 0;
    if (n == 0) return null;
    return Tooltip(
      message: 'Film ancora in programma oggi',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(color: CnvColors.surface2, borderRadius: BorderRadius.circular(999)),
        child: Text('$n', style: const TextStyle(fontSize: 12, color: CnvColors.textMuted)),
      ),
    );
  }
}
