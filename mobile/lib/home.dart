import 'package:flutter/material.dart';

import 'pages/page_placeholder.dart';
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
  CnvPage('In sala', Icons.local_movies_outlined, Icons.local_movies,
      'I film in programmazione nei cinema di Cosenza e Rende, con gli orari di oggi.'),
  CnvPage('In uscita', Icons.event_outlined, Icons.event,
      'I film annunciati dai cinema, in elenco e nel calendario del mese.'),
  CnvPage('Watchlist', Icons.bookmark_outline, Icons.bookmark,
      'I film segnati V o ? usciti dalle sale, da portare su Letterboxd.'),
  CnvPage('Visti', Icons.check_circle_outline, Icons.check_circle,
      'I film che hai visto al cinema, con le statistiche.'),
  CnvPage('Voti', Icons.how_to_vote_outlined, Icons.how_to_vote,
      'La copia dei voti, e più avanti accesso e notifiche.'),
];

/// The app's frame: title bar, the pages side by side (swipe to move) and the bottom menu.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  final _pager = PageController();
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
    return Scaffold(
      appBar: AppBar(title: const CnvTitle()),
      body: PageView(
        controller: _pager,
        onPageChanged: (index) => setState(() => _current = index),
        children: [for (final page in cnvPages) PagePlaceholder(page: page)],
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
        Text('CNV', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: CnvColors.accent)),
        SizedBox(width: 8),
        Text('Chi Ni Vidimu',
            style: TextStyle(fontSize: 13, fontStyle: FontStyle.italic, color: CnvColors.textMuted)),
      ],
    );
  }
}
