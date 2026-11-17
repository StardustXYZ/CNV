import 'package:flutter/material.dart';

import '../data/models.dart';
import '../theme.dart';
import 'save_file_io.dart' if (dart.library.js_interop) 'save_file_web.dart';

/// Gives the file: on the phone the share menu (Drive, email, Files…), where it can be
/// saved; in the browser a download. The tests replace it.
Future<void> Function(BuildContext context, String name, String content, String mime) shareTextFile = _shareTextFile;

Future<void> _shareTextFile(BuildContext context, String name, String content, String mime) async {
  try {
    await saveTextFile(name, content, mime);
  } catch (err) {
    if (context.mounted) say(context, 'Non riesco a preparare il file: $err');
  }
}

void say(BuildContext context, String text) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

/// "Hai importato il file su Letterboxd?"
Future<bool> confirmImported(BuildContext context) async =>
    await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Hai importato il file su Letterboxd?'),
        content: const Text('I film segnati come importati non finiscono nel prossimo file.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialog).pop(false), child: const Text('No')),
          FilledButton(onPressed: () => Navigator.of(dialog).pop(true), child: const Text('Sì, importati')),
        ],
      ),
    ) ==
    true;

/// Page title and the line that says what the page is for.
class PageHeader extends StatelessWidget {
  const PageHeader({super.key, required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(subtitle, style: const TextStyle(fontSize: 13, color: CnvColors.textMuted, height: 1.35)),
        ],
      ),
    );
  }
}

/// The box with the steps to bring the films to Letterboxd and its two buttons.
class ExportBox extends StatelessWidget {
  const ExportBox({
    super.key,
    required this.title,
    required this.count,
    required this.steps,
    required this.downloadLabel,
    required this.onDownload,
    required this.onImported,
  });

  final String title;
  final int count;
  final List<String> steps;
  final String downloadLabel;
  final VoidCallback onDownload;
  final VoidCallback onImported;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CnvColors.surface,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: CnvColors.accent.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('$title ($count)', style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          for (var i = 0; i < steps.length; i++)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text('${i + 1}. ${steps[i]}', style: const TextStyle(fontSize: 13, height: 1.35)),
            ),
          const SizedBox(height: 10),
          FilledButton.icon(onPressed: onDownload, icon: const Icon(Icons.download), label: Text(downloadLabel)),
          const SizedBox(height: 6),
          OutlinedButton.icon(
              onPressed: onImported, icon: const Icon(Icons.check), label: const Text('Li ho importati su Letterboxd')),
        ],
      ),
    );
  }
}

/// Films that cannot go in the file because TMDB does not know them.
class MissingTmdbNotice extends StatelessWidget {
  const MissingTmdbNotice({super.key, required this.films});

  final List<Film> films;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: CnvColors.yellow.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: CnvColors.yellow.withValues(alpha: 0.6)),
      ),
      child: Text(
        '${films.length} film senza abbinamento TMDB non sono nel file: '
        '${films.map((f) => f.title).join(', ')}. Sistemali dalla versione di CNV sul PC.',
        style: const TextStyle(fontSize: 13, height: 1.35),
      ),
    );
  }
}

/// A page with nothing to show yet.
class EmptyState extends StatelessWidget {
  const EmptyState(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 16),
      child: Text(text, textAlign: TextAlign.center, style: const TextStyle(color: CnvColors.textMuted, height: 1.4)),
    );
  }
}
