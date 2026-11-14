import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../data/personal.dart';
import '../data/repository.dart';
import '../data/schedule.dart';
import '../theme.dart';
import '../widgets/letterboxd_widgets.dart';
import 'account_page.dart';

/// "Voti": how many films have each vote, and the copy of the votes (save and restore,
/// also the one made by the web version). Login and notifications come later.
class VotiPage extends StatelessWidget {
  const VotiPage({super.key, required this.store});

  final DataStore store;

  @override
  Widget build(BuildContext context) {
    final personal = PersonalScope.of(context);
    final counts = {for (final v in votes) v: personal.votesById.values.where((x) => x == v).length};
    return RefreshIndicator(
      onRefresh: store.refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
        children: [
          const AccountSection(),
          const Text('I tuoi voti', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text(personal.linked ? 'Li vedi solo tu: sono su questo telefono e nel tuo account.' : 'Li vedi solo tu e restano su questo telefono.',
              style: TextStyle(fontSize: 13, color: CnvColors.textMuted)),
          const SizedBox(height: 12),
          Row(
            children: [
              for (final v in votes) ...[
                if (v != votes.first) const SizedBox(width: 8),
                Expanded(child: _CountBox(label: voteLabels[v]!, title: voteTitles[v]!, count: counts[v]!)),
              ],
            ],
          ),
          const SizedBox(height: 22),
          const Text('Copia dei voti', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text(
              'Salvala ogni tanto (su Drive, per email…): se cambi telefono o reinstalli l’app la ripristini da qui. '
              'Va bene anche la copia fatta con la versione web.',
              style: TextStyle(fontSize: 13, color: CnvColors.textMuted, height: 1.35)),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: () => _saveCopy(context, personal),
            icon: const Icon(Icons.save_alt),
            label: const Text('Salva una copia dei voti'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () => _restoreCopy(context, personal),
            icon: const Icon(Icons.restore),
            label: const Text('Ripristina da una copia'),
          ),
        ],
      ),
    );
  }

  Future<void> _saveCopy(BuildContext context, PersonalStore personal) async {
    final now = store.now;
    await shareTextFile(context, 'cnv-voti-${isoDate(now)}.json',
        personal.exportJson(savedAt: now.toUtc().toIso8601String()), 'application/json');
  }

  Future<void> _restoreCopy(BuildContext context, PersonalStore personal) async {
    final FilePickerResult? picked;
    try {
      picked = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: ['json'], withData: true);
    } catch (err) {
      if (context.mounted) say(context, 'Non riesco ad aprire i file: $err');
      return;
    }
    final bytes = picked?.files.single.bytes;
    if (bytes == null || !context.mounted) return;
    final text = utf8.decode(bytes, allowMalformed: true);
    final count = PersonalStore.votesIn(text);
    if (count < 0) {
      say(context, 'Il file non è una copia dei voti.');
      return;
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Ripristinare la copia?'),
        content: Text('La copia ha $count ${count == 1 ? 'voto' : 'voti'} e sostituisce i '
            '${personal.votesById.length} che hai ora su questo telefono.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialog).pop(false), child: const Text('Annulla')),
          FilledButton(onPressed: () => Navigator.of(dialog).pop(true), child: const Text('Ripristina')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final restored = await personal.importJson(text);
      final merged = store.data?.merged;
      if (merged != null && merged.isNotEmpty) await personal.applyMerges(merged);
      if (context.mounted) say(context, 'Ripristinati $restored ${restored == 1 ? 'voto' : 'voti'}.');
    } on FormatException catch (err) {
      if (context.mounted) say(context, err.message);
    }
  }
}

class _CountBox extends StatelessWidget {
  const _CountBox({required this.label, required this.title, required this.count});

  final String label;
  final String title;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
      decoration: BoxDecoration(
        color: CnvColors.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: CnvColors.border),
      ),
      child: Column(
        children: [
          Text('$count', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
          Text('$label · $title',
              textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: CnvColors.textMuted)),
        ],
      ),
    );
  }
}
