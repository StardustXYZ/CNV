import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'data/personal.dart';
import 'data/repository.dart';
import 'home.dart';
import 'theme.dart';

void main() => runApp(const CnvApp());

/// CNV (Chi Ni Vidimu): the films in the cinemas of Cosenza and Rende, on the phone.
class CnvApp extends StatefulWidget {
  const CnvApp({super.key, this.store, this.personal});

  final DataStore? store; // given by the tests; otherwise the app downloads the real data
  final PersonalStore? personal; // given by the tests; otherwise the votes saved on the phone

  @override
  State<CnvApp> createState() => _CnvAppState();
}

class _CnvAppState extends State<CnvApp> {
  late final DataStore _store = widget.store ?? DataStore(DataRepository());
  late final PersonalStore _personal = widget.personal ?? PersonalStore();

  @override
  void initState() {
    super.initState();
    _store.addListener(_applyMerges);
    if (widget.personal == null) _personal.load().then((_) => _applyMerges());
    if (widget.store == null) _store.start();
  }

  /// Votes given to a duplicate that the sync merged move to the film that absorbed it.
  void _applyMerges() {
    final merged = _store.data?.merged;
    if (merged != null && merged.isNotEmpty) _personal.applyMerges(merged);
  }

  @override
  void dispose() {
    _store.removeListener(_applyMerges);
    if (widget.store == null) _store.dispose();
    if (widget.personal == null) _personal.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Above the navigator: the film and cinema pages opened on top see the votes too
    return PersonalScope(
      store: _personal,
      child: MaterialApp(
        title: 'CNV',
        debugShowCheckedModeBanner: false,
        theme: cnvTheme(),
        locale: const Locale('it'),
        supportedLocales: const [Locale('it')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: HomeShell(store: _store),
      ),
    );
  }
}
