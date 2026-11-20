import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/format.dart';
import '../data/models.dart';
import '../data/personal.dart';
import '../theme.dart';
import 'spring_sheet.dart';

const _activeColors = {'V': CnvColors.green, '?': CnvColors.yellow, 'S': CnvColors.accent};

/// V / ? / ✓ of a film. Touching the current one removes it; marking ✓ asks where it was seen.
class VoteButtons extends StatelessWidget {
  const VoteButtons({super.key, required this.film, required this.data, required this.today});

  final Film film;
  final CnvData data;
  final String today; // programme day: after midnight a ✓ is still last night's

  @override
  Widget build(BuildContext context) {
    final personal = PersonalScope.of(context);
    final current = personal.vote(film.id);
    final seen = current == 'S' ? personal.seen[film.id] : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            for (final v in votes) ...[
              if (v != votes.first) const SizedBox(width: 6),
              Expanded(
                child: Tooltip(
                  message: current == v ? 'Togli il voto' : voteTitles[v]!,
                  child: _VoteButton(
                    label: voteLabels[v]!,
                    active: current == v,
                    color: _activeColors[v]!,
                    onTap: () async {
                      HapticFeedback.lightImpact();
                      final nowSeen = v == 'S' && current != 'S';
                      await personal.toggleVote(film.id, v, today: today);
                      if (nowSeen && context.mounted) await askWhereSeen(context, film, data, personal);
                    },
                  ),
                ),
              ),
            ],
          ],
        ),
        if (seen != null)
          Padding(
            padding: const EdgeInsets.only(top: 5),
            child: Text(
              '✓ Visto${seen.date != null ? ' il ${longDate(seen.date!, today)}' : ''}${seen.cinema != null ? ' · ${data.cinemasBySlug[seen.cinema]?.name ?? seen.cinema}' : ''}',
              style: const TextStyle(fontSize: 12, color: CnvColors.accent),
            ),
          ),
      ],
    );
  }
}

class _VoteButton extends StatelessWidget {
  const _VoteButton({required this.label, required this.active, required this.color, required this.onTap});

  final String label;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: active ? color : Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(6),
        side: BorderSide(color: active ? color : const Color(0xFF444444)),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(6),
        onTap: onTap,
        child: SizedBox(
          height: 34,
          child: Center(
            child: Text(label,
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 15,
                  color: active ? (color == CnvColors.green ? Colors.white : Colors.black) : CnvColors.text,
                )),
          ),
        ),
      ),
    );
  }
}

/// "Dove l'hai visto?": the cinemas that show the film (all of them if none), or "Salta".
Future<void> askWhereSeen(BuildContext context, Film film, CnvData data, PersonalStore personal) async {
  final showing = {for (final s in data.shows) if (s.filmId == film.id) s.cinema};
  final cinemas = [for (final c in data.cinemas) if (showing.isEmpty || showing.contains(c.slug)) c];
  final choice = await showSpringBottomSheet<String>(
    context: context,
    builder: (sheet) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Text("Dove hai visto ${film.title}?", style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          ),
          for (final c in cinemas)
            ListTile(leading: const Icon(Icons.theaters), title: Text(c.name), onTap: () => Navigator.of(sheet).pop(c.slug)),
          ListTile(
            leading: const Icon(Icons.close, color: CnvColors.textMuted),
            title: const Text('Salta', style: TextStyle(color: CnvColors.textMuted)),
            onTap: () => Navigator.of(sheet).pop(''),
          ),
        ],
      ),
    ),
  );
  if (choice != null && choice.isNotEmpty) await personal.setSeen(film.id, cinema: choice);
}
