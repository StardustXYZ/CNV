import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../data/device_words.dart';
import '../theme.dart';
import '../widgets/bottom_padding.dart';

/// "Privacy": what CNV keeps, where, who sees it, and how to delete it. In plain words.
class PrivacyPage extends StatelessWidget {
  const PrivacyPage({super.key});

  static const _sections = [
    (
      'Senza account',
      'I voti, i film visti e quello che hai portato su Letterboxd restano solo $onThisDevice. '
          'CNV scarica i programmi dei cinema e le locandine (da TMDB), ma non manda niente di tuo.'
    ),
    (
      'Con l’account',
      'L’account usa Firebase, un servizio di Google. Lì sono salvati: la tua email (e il nome, se '
          'entri con Google), i tuoi voti, i film visti con giorno e cinema, cosa hai già portato su '
          'Letterboxd, la scelta delle notifiche e un codice per ogni telefono dove le hai attivate.'
    ),
    (
      'Chi vede i tuoi dati',
      'Nell’app nessun altro: ogni account legge e scrive solo i suoi dati. Chi gestisce CNV vede '
          'nell’app solo la lista delle email ammesse, non i voti. Ha però accesso alla console di '
          'Firebase, dove i dati si potrebbero vedere: non li guarda, non li condivide e non li usa per altro.'
    ),
    (
      'Notifiche',
      'Ogni notte un programma su GitHub controlla i film nuovi in sala e, se le hai attivate, ti manda '
          'la notifica, mettendo per primi i film che hai segnato V. Per farlo legge la tua scelta, i tuoi '
          'voti e i codici dei tuoi telefoni; non li salva altrove e non scrive nel registro né la tua '
          'email né i tuoi voti.'
    ),
    (
      'Cosa non fa',
      'Niente pubblicità, niente statistiche su come usi l’app, niente dati venduti o dati a terzi '
          'oltre a Google (Firebase) e GitHub, che servono per far funzionare account e notifiche.'
    ),
    (
      'Cancellare i dati',
      'Nella pagina Voti, con l’account aperto, “Elimina l’account” cancella da Firebase i tuoi voti, i '
          'telefoni registrati e l’account stesso. '
          '${kIsWeb ? 'I voti nel browser restano finché non cancelli i dati del sito; senza account basta '
              'cancellarli.' : 'I voti sul telefono restano, finché non disinstalli l’app. Senza account basta '
              'disinstallare l’app.'} '
          'Per qualsiasi domanda scrivi a chi ti ha dato CNV.'
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Title(
      title: 'Privacy · CNV',
      color: CnvColors.background,
      child: Scaffold(
      appBar: AppBar(title: const Text('Privacy')),
      body: ListView(
        padding: EdgeInsets.fromLTRB(16, 12, 16, BottomPadding.of(context, minimum: 28)),
        children: [
          const Text('Quali dati usa CNV', style: TextStyle(fontSize: 21, fontWeight: FontWeight.w800)),
          for (final (title, text) in _sections) ...[
            const SizedBox(height: 16),
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            Text(text, style: const TextStyle(fontSize: 14, height: 1.45, color: CnvColors.text)),
          ],
        ],
      ),
    ));
  }
}
