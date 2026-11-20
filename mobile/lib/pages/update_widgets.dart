import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../data/updates.dart';
import '../theme.dart';
import '../widgets/letterboxd_widgets.dart' show say;
import 'privacy_page.dart';

/// Gives the pages the update check (null in the tests).
class UpdateScope extends InheritedNotifier<UpdateStore> {
  const UpdateScope({super.key, required UpdateStore? store, required super.child}) : super(notifier: store);

  static UpdateStore? of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<UpdateScope>()?.notifier;
}

/// Opens the APK in the browser, which downloads it; then the user opens the file to install.
Future<void> downloadUpdate(BuildContext context, AppRelease release) async {
  final opened = await launchUrl(Uri.parse(release.apkUrl), mode: LaunchMode.externalApplication);
  if (!context.mounted) return;
  say(
    context,
    opened
        ? 'Quando il download finisce, apri il file e tocca Aggiorna. Se Android lo chiede, permetti '
            'l’installazione dal browser. I tuoi voti restano.'
        : 'Non riesco ad aprire il browser. Scarica la versione da $releasesPage',
  );
}

/// The notice at the top of the app when a newer version is out.
class UpdateBanner extends StatelessWidget {
  const UpdateBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final store = UpdateScope.of(context);
    if (store == null || !store.showNotice) return const SizedBox();
    final release = store.available!;
    return Material(
      color: CnvColors.accent.withValues(alpha: 0.16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 8, 6, 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.system_update, color: CnvColors.accent),
                const SizedBox(width: 10),
                Expanded(
                  child: Text('È uscita la versione ${release.version} di CNV',
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
              ],
            ),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(onPressed: store.dismiss, child: const Text('Non ora')),
                FilledButton(onPressed: () => downloadUpdate(context, release), child: const Text('Scarica')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// At the bottom of the Voti page: the version, the check for a new one, and the privacy note.
class AppInfoBox extends StatelessWidget {
  const AppInfoBox({super.key});

  @override
  Widget build(BuildContext context) {
    final store = UpdateScope.of(context);
    final children = <Widget>[
      const Text('App', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
      const SizedBox(height: 4),
    ];
    if (store != null) {
      final release = store.available;
      children.add(Text(
        release != null
            ? 'Hai la versione ${store.versionLabel}: è uscita la ${release.version}.'
            : store.checkedAt != null
                ? 'Hai la versione ${store.versionLabel}, l’ultima uscita.'
                : 'Versione ${store.versionLabel}',
        style: const TextStyle(fontSize: 13, color: CnvColors.textMuted),
      ));
      if (store.problem != null) {
        children.add(Text(store.problem!, style: const TextStyle(fontSize: 12, color: CnvColors.yellow)));
      }
      children.add(const SizedBox(height: 6));
      children.add(release != null
          ? FilledButton.icon(
              onPressed: () => downloadUpdate(context, release),
              icon: const Icon(Icons.download),
              label: Text('Scarica la versione ${release.version}'),
            )
          : OutlinedButton.icon(
              onPressed: store.checking ? null : store.check,
              icon: const Icon(Icons.refresh),
              label: Text(store.checking ? 'Controllo…' : 'Controlla se c’è una versione nuova'),
            ));
    }
    children.add(TextButton.icon(
      onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const PrivacyPage())),
      icon: const Icon(Icons.privacy_tip_outlined, size: 18),
      label: const Text('Privacy: quali dati usa CNV'),
    ));
    return Padding(
      padding: const EdgeInsets.only(top: 22),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
  }
}
