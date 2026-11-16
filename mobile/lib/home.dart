import 'package:flutter/material.dart';

import 'data/repository.dart';
import 'pages/cinema_page.dart';
import 'pages/in_sala_page.dart';
import 'pages/in_uscita_page.dart';
import 'pages/page_placeholder.dart';
import 'pages/update_widgets.dart';
import 'pages/visti_page.dart';
import 'pages/voti_page.dart';
import 'pages/watchlist_page.dart';
import 'theme.dart';

/// One page of the app, as listed in the bottom menu.
class CnvPage {
  const CnvPage(this.label, this.icon, this.selectedIcon, this.description);

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final String description;
}

/// The pages, in the same order as the menu of the web version.
const cnvPages = [
  CnvPage(
    'In sala',
    Icons.local_movies_outlined,
    Icons.local_movies,
    'I film in programmazione nei cinema di Cosenza e Rende, con gli orari di oggi.',
  ),
  CnvPage(
    'In uscita',
    Icons.event_outlined,
    Icons.event,
    'I film annunciati dai cinema, in elenco e nel calendario del mese.',
  ),
  CnvPage(
    'Watchlist',
    Icons.bookmark_outline,
    Icons.bookmark,
    'I film segnati V o ? usciti dalle sale, da portare su Letterboxd.',
  ),
  CnvPage(
    'Visti',
    Icons.check_circle_outline,
    Icons.check_circle,
    'I film che hai visto al cinema, con le statistiche.',
  ),
  CnvPage(
    'Voti',
    Icons.how_to_vote_outlined,
    Icons.how_to_vote,
    'I tuoi voti, la loro copia, l’account e le notifiche.',
  ),
];

/// The app's frame: title bar with the data status, the pages side by side (swipe to
/// move) and the bottom menu.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.store});

  final DataStore store;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  final _pager = PageController();
  late final DataStore _store = widget.store;
  int _current = 0;

  @override
  void dispose() {
    _pager.dispose();
    super.dispose();
  }

  void _goTo(int index) {
    setState(() => _current = index);
    _pager.animateToPage(index, duration: const Duration(milliseconds: 250), curve: Curves.easeOutCubic);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _store,
      builder: (context, _) {
        final ready = _store.data != null;
        return Scaffold(
          drawer: CinemaDrawer(store: _store), // ☰: the cinemas, as the menu of the web version
          appBar: AppBar(
            title: const CnvTitle(),
            actions: [
              IconButton(
                tooltip: 'Aggiorna i dati',
                onPressed: _store.refreshing ? null : _store.refresh,
                icon: const Icon(Icons.refresh),
              ),
            ],
            bottom: DataStatusBar(store: _store),
          ),
          body: Column(
            children: [
              const UpdateBanner(),
              Expanded(
                child: _store.state == LoadState.error
                    ? NoDataMessage(onRetry: _store.refresh, retrying: _store.refreshing)
                    : PageView(
                        controller: _pager,
                        onPageChanged: (index) => setState(() => _current = index),
                        children: [
                          if (ready) InSalaPage(store: _store) else PagePlaceholder(page: cnvPages[0]),
                          if (ready) InUscitaPage(store: _store) else PagePlaceholder(page: cnvPages[1]),
                          if (ready) WatchlistPage(store: _store) else PagePlaceholder(page: cnvPages[2]),
                          if (ready) VistiPage(store: _store) else PagePlaceholder(page: cnvPages[3]),
                          VotiPage(store: _store),
                        ],
                      ),
              ),
            ],
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _current,
            onDestinationSelected: _goTo,
            destinations: [
              for (final page in cnvPages)
                NavigationDestination(icon: Icon(page.icon), selectedIcon: Icon(page.selectedIcon), label: page.label),
            ],
          ),
        );
      },
    );
  }
}

/// "🎬 CNV Chi Ni Vidimu", as in the web version.
class CnvTitle extends StatelessWidget {
  const CnvTitle({super.key});

  @override
  Widget build(BuildContext context) {
    return const Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        Text('🎬 ', style: TextStyle(fontSize: 20)),
        Text(
          'CNV',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: CnvColors.accent),
        ),
        SizedBox(width: 8),
        // On a narrow phone, with the menu and refresh buttons, it shortens instead of overflowing
        Flexible(
          child: Text(
            'Chi Ni Vidimu',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 13, fontStyle: FontStyle.italic, color: CnvColors.textMuted),
          ),
        ),
      ],
    );
  }
}

/// Under the title: when the data was made, and whether it is the saved copy or old.
class DataStatusBar extends StatelessWidget implements PreferredSizeWidget {
  const DataStatusBar({super.key, required this.store});

  final DataStore store;

  @override
  Size get preferredSize => const Size.fromHeight(26);

  static String _two(int n) => n.toString().padLeft(2, '0');

  @override
  Widget build(BuildContext context) {
    final data = store.data;
    String text;
    Color color = CnvColors.textMuted;
    if (data == null) {
      text = store.refreshing ? 'Scarico i dati…' : 'Nessun dato';
    } else {
      final when = data.generatedAt.toLocal();
      text = 'Dati aggiornati il ${when.day}/${when.month} alle ${_two(when.hour)}:${_two(when.minute)}';
      if (store.offline) {
        text += ' · senza connessione';
        color = CnvColors.yellow;
      } else if (store.stale) {
        text += ' · dati vecchi';
        color = CnvColors.yellow;
      }
    }
    return SizedBox(
      height: preferredSize.height,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Row(
          children: [
            Expanded(
              child: Text(
                text,
                style: TextStyle(fontSize: 12, color: color),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (store.refreshing && data != null)
              const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 1.5)),
          ],
        ),
      ),
    );
  }
}

/// No data at all: never downloaded and no saved copy.
class NoDataMessage extends StatelessWidget {
  const NoDataMessage({super.key, required this.onRetry, required this.retrying});

  final VoidCallback onRetry;
  final bool retrying;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: CnvColors.textMuted),
            const SizedBox(height: 12),
            const Text(
              'Non riesco a scaricare i dati.\nControlla la connessione e riprova.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16, height: 1.4),
            ),
            const SizedBox(height: 16),
            FilledButton(onPressed: retrying ? null : onRetry, child: Text(retrying ? 'Riprovo…' : 'Riprova')),
          ],
        ),
      ),
    );
  }
}
