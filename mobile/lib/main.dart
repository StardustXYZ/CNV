import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'data/account.dart';
import 'data/firebase_account.dart';
import 'data/firebase_push.dart';
import 'data/notifications.dart';
import 'data/personal.dart';
import 'data/repository.dart';
import 'data/sync.dart';
import 'home.dart';
import 'pages/account_page.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  AccountBackend? backend;
  PushBackend? push;
  try {
    await Firebase.initializeApp(); // from android/app/google-services.json
    backend = FirebaseAccountBackend();
    push = FirebasePushBackend();
  } catch (err) {
    debugPrint('Firebase non avviato: $err'); // CNV works anyway, without the account
  }
  final account = AccountStore(backend);
  runApp(
    CnvApp(
      account: account,
      notifications: backend != null && push != null ? NotificationStore(account, backend, push) : null,
      foreground: push?.foreground(),
    ),
  );
}

/// CNV (Chi Ni Vidimu): the films in the cinemas of Cosenza and Rende, on the phone.
class CnvApp extends StatefulWidget {
  const CnvApp({super.key, this.store, this.personal, this.account, this.notifications, this.foreground});

  final DataStore? store; // given by the tests; otherwise the app downloads the real data
  final PersonalStore? personal; // given by the tests; otherwise the votes saved on the phone
  final AccountStore? account; // without it, no account (as in the tests)
  final NotificationStore? notifications; // without it, no notifications
  final Stream<String>? foreground; // notifications arrived with the app open

  @override
  State<CnvApp> createState() => _CnvAppState();
}

class _CnvAppState extends State<CnvApp> {
  late final DataStore _store = widget.store ?? DataStore(DataRepository());
  late final PersonalStore _personal = widget.personal ?? PersonalStore();
  late final AccountStore _account = widget.account ?? AccountStore(null);
  VoteSync? _sync;
  final _messenger = GlobalKey<ScaffoldMessengerState>();
  StreamSubscription<String>? _foreground;

  @override
  void initState() {
    super.initState();
    _store.addListener(_applyMerges);
    if (widget.personal == null) {
      // The votes saved on the phone first, then the account: they are merged, not replaced
      _personal.load().then((_) {
        _applyMerges();
        if (mounted) _sync = VoteSync(_account, _personal);
      });
    } else {
      _sync = VoteSync(_account, _personal);
    }
    if (widget.store == null) _store.start();
    // With the app open Android does not show them: a message at the bottom instead
    _foreground = widget.foreground?.listen(
      (text) =>
          _messenger.currentState?.showSnackBar(SnackBar(content: Text(text), duration: const Duration(seconds: 8))),
    );
  }

  /// Votes given to a duplicate that the sync merged move to the film that absorbed it.
  void _applyMerges() {
    final merged = _store.data?.merged;
    if (merged != null && merged.isNotEmpty) _personal.applyMerges(merged);
  }

  @override
  void dispose() {
    _store.removeListener(_applyMerges);
    _sync?.dispose();
    _foreground?.cancel();
    if (widget.store == null) _store.dispose();
    if (widget.personal == null) _personal.dispose();
    if (widget.account == null) _account.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Above the navigator: the film and cinema pages opened on top see the votes too
    return NotificationScope(
      store: widget.notifications,
      child: AccountScope(
        store: _account,
        child: PersonalScope(
          store: _personal,
          child: MaterialApp(
            title: 'CNV',
            debugShowCheckedModeBanner: false,
            scaffoldMessengerKey: _messenger,
            theme: cnvTheme(),
            locale: const Locale('it'),
            supportedLocales: const [Locale('it')],
            localizationsDelegates: GlobalMaterialLocalizations.delegates,
            home: HomeShell(store: _store),
          ),
        ),
      ),
    );
  }
}
