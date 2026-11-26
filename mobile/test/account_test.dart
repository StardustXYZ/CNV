import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/account.dart';
import 'package:cnv/data/personal.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/account_page.dart';

import 'personal_test.dart' show MemoryPersonal;
import 'programme_test.dart' show sample;
import 'sync_test.dart' show FakeCloud, FakeRemote;
import 'widget_test.dart' show storeWith;

/// Firebase as the rules would answer: "capo" is the administrator, amico@example.com is admitted.
class FakeBackend implements AccountBackend {
  final _users = StreamController<AccountUser?>.broadcast();
  AccountUser? _current;
  List<String> allowed = ['amico@example.com'];
  final accounts = <String, String>{'amico@example.com': 'segreta1'}; // e-mail -> password
  final verifiedEmails = <String>{'amico@example.com'};
  final sent = <String>[];
  bool offline = false;

  void _set(AccountUser? u) {
    _current = u;
    _users.add(u);
  }

  AccountUser _emailUser(String email) =>
      AccountUser(uid: email.split('@').first, email: email, verified: verifiedEmails.contains(email));

  @override
  Stream<AccountUser?> userChanges() => _users.stream;

  @override
  AccountUser? get current => _current;

  @override
  Future<void> signInWithGoogle() async =>
      _set(const AccountUser(uid: 'capo', email: 'capo@gmail.com', verified: true, name: 'Capo', google: true));

  @override
  Future<void> signInWithEmail(String email, String password) async {
    if (accounts[email] != password) throw const AccountError('Email o password sbagliate.');
    _set(_emailUser(email));
  }

  @override
  Future<void> register(String email, String password) async {
    if (accounts.containsKey(email)) throw const AccountError('Esiste già un account con questa email.');
    accounts[email] = password;
    sent.add('conferma:$email');
    _set(_emailUser(email));
  }

  @override
  Future<void> sendPasswordReset(String email) async => sent.add('password:$email');

  @override
  Future<void> sendVerification() async => sent.add('conferma:${_current!.email}');

  @override
  Future<AccountUser?> reload() async {
    final u = _current == null ? null : _emailUser(_current!.email);
    if (u != null) _current = u;
    return u;
  }

  @override
  Future<void> signOut() async => _set(null);

  @override
  Future<bool> isAdmitted(String uid) async {
    if (offline) throw Exception('unavailable');
    return uid == 'capo' || allowed.contains(_current?.email.toLowerCase());
  }

  @override
  Future<List<String>?> allowList() async => _current?.uid == 'capo' ? [...allowed] : null;

  @override
  Future<void> saveAllowList(List<String> emails) async => allowed = emails;

  final cloud = FakeCloud();

  @override
  PersonalRemote personalRemote(String uid) => FakeRemote(cloud, uid);

  final notify = <String, String>{}; // uid -> choice
  final phones = <String, Map<String, String>>{}; // uid -> phone -> token

  @override
  Future<String?> notifyMode(String uid) async => notify[uid];

  @override
  Future<void> setNotifyMode(String uid, String mode) async => notify[uid] = mode;

  final lastDaysOn = <String, bool>{}; // uid -> "ultimi giorni"

  @override
  Future<bool> lastDays(String uid) async => lastDaysOn[uid] ?? false;

  @override
  Future<void> setLastDays(String uid, bool on) async => lastDaysOn[uid] = on;

  @override
  Future<void> savePhone(String uid, String phone, String token) async => (phones[uid] ??= {})[phone] = token;

  @override
  Future<void> removePhone(String uid, String phone) async => phones[uid]?.remove(phone);

  final deleted = <String>[];

  @override
  Future<void> deleteAccount() async {
    final uid = _current!.uid;
    phones.remove(uid);
    notify.remove(uid);
    lastDaysOn.remove(uid);
    cloud.docs.remove(uid);
    deleted.add(uid);
    _set(null);
  }
}

Future<void> settle() => Future<void>.delayed(Duration.zero);

void main() {
  group('the account store', () {
    test('Google: admitted, and the administrator gets the list', () async {
      final store = AccountStore(FakeBackend());
      await store.signInWithGoogle();
      await settle();
      expect(store.user!.email, 'capo@gmail.com');
      expect(store.admission, Admission.admitted);
      expect(store.isAdmin, isTrue);
      expect(store.allowed, ['amico@example.com']);
      await store.signOut();
      await settle();
      expect(store.user, isNull);
      expect(store.admission, Admission.none);
      expect(store.isAdmin, isFalse);
    });

    test('a new e-mail account waits for the confirmation, then is checked', () async {
      final backend = FakeBackend()..allowed.add('nuovo@example.com');
      final store = AccountStore(backend);
      await store.register(' nuovo@example.com ', 'password');
      await settle();
      expect(backend.sent, ['conferma:nuovo@example.com']);
      expect(store.user!.verified, isFalse);
      expect(store.admission, Admission.none); // not checked before the confirmation
      expect(await store.reloadVerified(), isFalse);

      backend.verifiedEmails.add('nuovo@example.com');
      expect(await store.reloadVerified(), isTrue);
      await settle();
      expect(store.admission, Admission.admitted);
      expect(store.isAdmin, isFalse);
    });

    test('not in the list, and no connection', () async {
      final backend = FakeBackend()
        ..accounts['estraneo@example.com'] = 'password'
        ..verifiedEmails.add('estraneo@example.com');
      final store = AccountStore(backend);
      await store.signInWithEmail('estraneo@example.com', 'password');
      await settle();
      expect(store.admission, Admission.notAdmitted);
      backend.offline = true;
      await store.checkAdmission();
      expect(store.admission, Admission.error);
    });

    test('wrong password: the error has words for the user', () async {
      final store = AccountStore(FakeBackend());
      await expectLater(store.signInWithEmail('amico@example.com', 'no'), throwsA(isA<AccountError>()));
      expect(store.busy, isFalse);
    });

    test('the administrator saves the list in lower case, without repeats, sorted', () async {
      final backend = FakeBackend();
      final store = AccountStore(backend);
      await store.signInWithGoogle();
      await settle();
      await store.setAllowList(['Zeta@Example.com', 'amico@example.com', ' ', 'zeta@example.com']);
      expect(backend.allowed, ['amico@example.com', 'zeta@example.com']);
      expect(store.allowed, backend.allowed);
    });

    test('without Firebase the account is not available', () async {
      final store = AccountStore(null);
      expect(store.available, isFalse);
      await expectLater(store.signInWithGoogle(), throwsA(isA<AccountError>()));
    });

    test('e-mail addresses', () {
      expect(looksLikeEmail('a@b.it'), isTrue);
      expect(looksLikeEmail(' a.b@c.example.com '), isTrue);
      expect(looksLikeEmail('a@b'), isFalse);
      expect(looksLikeEmail('a b@c.it'), isFalse);
    });
  });

  group('the Account box of the Voti page', () {
    Future<FakeBackend> openVoti(WidgetTester tester, {AccountStore? account}) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.6;
      addTearDown(tester.view.reset);
      final backend = FakeBackend();
      await tester.pumpWidget(CnvApp(
        store: await storeWith(LoadResult(sample(), offline: false)),
        personal: MemoryPersonal(),
        account: account ?? AccountStore(backend),
      ));
      await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Voti')));
      await tester.pumpAndSettle();
      return backend;
    }

    testWidgets('without Firebase it says so', (tester) async {
      await openVoti(tester, account: AccountStore(null));
      expect(find.textContaining("L'accesso non è disponibile"), findsOneWidget);
    });

    testWidgets('Google: admitted, administrator, adds an e-mail, signs out', (tester) async {
      final backend = await openVoti(tester);
      await tester.tap(find.text('Accedi con Google'));
      await tester.pumpAndSettle();
      expect(find.text('Capo · capo@gmail.com'), findsOneWidget);
      expect(find.textContaining('Sei nella lista'), findsOneWidget);
      expect(find.text('Codice utente: capo'), findsOneWidget);

      await tester.tap(find.text('Gestisci gli ammessi (1)'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Nuovo@Example.com');
      await tester.tap(find.text('Aggiungi'));
      await tester.pumpAndSettle();
      expect(backend.allowed, ['amico@example.com', 'nuovo@example.com']);
      expect(find.text('nuovo@example.com'), findsOneWidget);

      await tester.tap(find.byTooltip('Togli amico@example.com'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Togli'));
      await tester.pumpAndSettle();
      expect(backend.allowed, ['nuovo@example.com']);

      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.text('Gestisci gli ammessi (1)'), findsOneWidget);
      await tester.tap(find.text('Esci dall’account'));
      await tester.pumpAndSettle();
      expect(find.textContaining('I voti restano su questo telefono'), findsOneWidget);
      await tester.tap(find.text('Esci'));
      await tester.pumpAndSettle();
      expect(find.text('Accedi con Google'), findsOneWidget);
    });

    testWidgets('a new e-mail account: the form checks it, then the confirmation', (tester) async {
      final backend = await openVoti(tester);
      await tester.tap(find.text('Accedi con email e password'));
      await tester.pumpAndSettle();
      expect(find.byType(EmailLoginPage), findsOneWidget);
      await tester.tap(find.text('Sono nuovo'));
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'Email'), 'nuovo@example');
      await tester.enterText(find.widgetWithText(TextField, 'Password'), '123');
      await tester.tap(find.text('Crea l’account'));
      await tester.pumpAndSettle();
      expect(find.text('Scrivi un indirizzo email valido.'), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextField, 'Email'), 'nuovo@example.com');
      await tester.tap(find.text('Crea l’account'));
      await tester.pumpAndSettle();
      expect(find.text('La password deve avere almeno 6 caratteri.'), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextField, 'Password'), 'password');
      await tester.tap(find.text('Crea l’account'));
      await tester.pumpAndSettle();
      expect(find.byType(EmailLoginPage), findsNothing); // back to Voti
      expect(find.textContaining('Ti ho mandato un’email di conferma a nuovo@example.com'), findsOneWidget);

      await tester.tap(find.text('Ho confermato'));
      await tester.pumpAndSettle();
      expect(find.text('L’email non risulta ancora confermata.'), findsOneWidget);

      backend.verifiedEmails.add('nuovo@example.com'); // confirmed, but nobody added it to the list
      await tester.tap(find.text('Ho confermato'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Non sei ancora nella lista'), findsOneWidget);
      backend.allowed.add('nuovo@example.com');
      await tester.tap(find.text('Riprova'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Sei nella lista'), findsOneWidget);
      expect(find.textContaining('Gestisci gli ammessi'), findsNothing);
    });

    testWidgets('deleting the account: confirmed, data gone, the votes on the phone stay', (tester) async {
      final backend = await openVoti(tester);
      await tester.tap(find.text('Accedi con Google'));
      await tester.pumpAndSettle();
      backend.cloud.docs['capo'] = {'votes': {'1': 'V'}};
      await tester.ensureVisible(find.text('Elimina l’account'));
      await tester.tap(find.text('Elimina l’account'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Non si può annullare'), findsOneWidget);
      await tester.tap(find.text('Annulla'));
      await tester.pumpAndSettle();
      expect(backend.deleted, isEmpty);

      await tester.tap(find.text('Elimina l’account'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Elimina'));
      await tester.pumpAndSettle();
      expect(backend.deleted, ['capo']);
      expect(backend.cloud.docs['capo'], isNull);
      expect(find.text('Account eliminato.'), findsOneWidget);
      expect(find.text('Accedi con Google'), findsOneWidget);
    });

    testWidgets('wrong password and the forgotten one', (tester) async {
      final backend = await openVoti(tester);
      await tester.tap(find.text('Accedi con email e password'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Password dimenticata?'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Scrivi prima la tua email'), findsOneWidget);
      await tester.enterText(find.widgetWithText(TextField, 'Email'), 'amico@example.com');
      await tester.tap(find.text('Password dimenticata?'));
      await tester.pumpAndSettle();
      expect(backend.sent, ['password:amico@example.com']);

      await tester.enterText(find.widgetWithText(TextField, 'Password'), 'sbagliata');
      await tester.tap(find.text('Accedi'));
      await tester.pumpAndSettle();
      expect(find.text('Email o password sbagliate.'), findsOneWidget);
      expect(find.byType(EmailLoginPage), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextField, 'Password'), 'segreta1');
      await tester.tap(find.text('Accedi'));
      await tester.pumpAndSettle();
      expect(find.text('amico@example.com'), findsOneWidget);
      expect(find.textContaining('Sei nella lista'), findsOneWidget);
    });
  });
}
