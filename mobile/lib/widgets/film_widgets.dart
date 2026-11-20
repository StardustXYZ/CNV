import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/format.dart';
import '../data/models.dart';
import '../data/programme.dart';
import '../data/schedule.dart';
import '../theme.dart';

/// Opens a cinema's page (where to buy the ticket) in the browser.
Future<void> openLink(BuildContext context, String url) async {
  final uri = Uri.tryParse(url);
  final opened = uri != null && uri.hasScheme && await launchUrl(uri, mode: LaunchMode.externalApplication);
  if (!opened && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Non riesco ad aprire la pagina del cinema')));
  }
}

/// The film's poster (kept on the phone for use without connection), or 🎬 when there is none.
/// Without [width] it fills the width it is given, always 2:3.
class Poster extends StatelessWidget {
  const Poster({super.key, required this.url, this.width});

  final String? url;
  final double? width;

  @override
  Widget build(BuildContext context) {
    final placeholder = Container(
      color: CnvColors.surface2,
      alignment: Alignment.center,
      child: Text('🎬', style: TextStyle(fontSize: width == null ? 14 : width! / 3)),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: SizedBox(
        width: width,
        child: AspectRatio(
          aspectRatio: 2 / 3,
          child: url == null
            ? placeholder
            : kIsWeb
                // TMDB does not let a page read its images, only show them: a plain image
                ? Image.network(
                    url!,
                    fit: BoxFit.cover,
                    webHtmlElementStrategy: WebHtmlElementStrategy.prefer,
                    loadingBuilder: (_, image, progress) => AnimatedSwitcher(
                      duration: const Duration(milliseconds: 200),
                      child: KeyedSubtree(
                        key: ValueKey(progress == null),
                        child: progress == null ? image : placeholder,
                      ),
                    ),
                    errorBuilder: (_, _, _) => placeholder,
                  )
                : CachedNetworkImage(
                imageUrl: url!,
                fit: BoxFit.cover,
                  placeholder: (_, _) => placeholder,
                  errorWidget: (_, _, _) => placeholder,
                ),
        ),
      ),
    );
  }
}

/// "2026 · Commedia · 1h 54m", plus "Evento" for special screenings.
class FilmMeta extends StatelessWidget {
  const FilmMeta({super.key, required this.film});

  final Film film;

  @override
  Widget build(BuildContext context) {
    final parts = [
      if (film.year != null) '${film.year}',
      if (film.genre != null) film.genre!,
      if (film.runtime != null) formatRuntime(film.runtime!),
    ];
    return Wrap(
      spacing: 8,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (parts.isNotEmpty) Text(parts.join(' · '), style: const TextStyle(fontSize: 13, color: CnvColors.textMuted)),
        if (film.event)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(border: Border.all(color: CnvColors.accent), borderRadius: BorderRadius.circular(4)),
            child: const Text('Evento', style: TextStyle(fontSize: 11, color: CnvColors.accent)),
          ),
      ],
    );
  }
}

/// A show time: the start, and under it the estimated end. Touching it opens the purchase page.
class ShowTimeChip extends StatelessWidget {
  const ShowTimeChip({super.key, required this.show});

  final UpcomingShow show;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: CnvColors.surface2,
      borderRadius: BorderRadius.circular(6),
      child: InkWell(
        borderRadius: BorderRadius.circular(6),
        onTap: show.url.isEmpty ? null : () => openLink(context, show.url),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(hhmm(show.start), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
              if (show.end != null)
                Text('→${hhmm(show.end!)}', style: const TextStyle(fontSize: 11, color: CnvColors.textMuted)),
              if (show.originalLanguage || show.age != null)
                Text.rich(
                  TextSpan(children: [
                    if (show.originalLanguage)
                      const TextSpan(text: 'V.O.', style: TextStyle(color: CnvColors.accent)),
                    if (show.originalLanguage && show.age != null) const TextSpan(text: ' '),
                    if (show.age != null) TextSpan(text: '${show.age}+', style: const TextStyle(color: CnvColors.yellow)),
                  ]),
                  style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One sala and its show times.
class SalaRow extends StatelessWidget {
  const SalaRow({super.key, required this.sala, required this.shows});

  final String sala;
  final List<UpcomingShow> shows;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 76,
            child: Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(sala.isEmpty ? 'Sala' : sala,
                  style: const TextStyle(fontSize: 13, color: CnvColors.textMuted), overflow: TextOverflow.ellipsis),
            ),
          ),
          Expanded(child: Wrap(spacing: 6, runSpacing: 6, children: [for (final s in shows) ShowTimeChip(show: s)])),
        ],
      ),
    );
  }
}

/// The salas of a cinema, each with its shows, the earliest first.
class SalaList extends StatelessWidget {
  const SalaList({super.key, required this.bySala});

  final Map<String, List<UpcomingShow>> bySala;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [for (final e in sortedSalas(bySala)) SalaRow(sala: e.key, shows: e.value)],
    );
  }
}

/// Warning for cinemas whose site did not answer at the last update.
class NotUpdatedNotice extends StatelessWidget {
  const NotUpdatedNotice({super.key, required this.data, this.cinema});

  final CnvData data;
  final String? cinema; // only this cinema's warning

  @override
  Widget build(BuildContext context) {
    final list = [
      for (final e in data.notUpdated.entries)
        if (data.cinemasBySlug.containsKey(e.key) && (cinema == null || e.key == cinema)) e,
    ];
    if (list.isEmpty) return const SizedBox.shrink();
    final today = programmeDay(DateTime.now());
    final names = [
      for (final e in list) '${data.cinemasBySlug[e.key]!.name}${e.value != null ? ' (orari del ${longDate(e.value!, today)})' : ''}',
    ].join(', ');
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CnvColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: const Border(left: BorderSide(color: CnvColors.red, width: 3)),
      ),
      child: Text(
        "⚠️ All'ultimo aggiornamento non ha risposto il sito di $names: "
        '${list.length == 1 ? 'i suoi orari' : 'i loro orari'} potrebbero essere cambiati. '
        'Controlla sul sito del cinema prima di andare.',
        style: const TextStyle(fontSize: 13, height: 1.4),
      ),
    );
  }
}
