import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/account.dart';
import 'package:cnv/data/notifications.dart';
import 'package:cnv/data/repository.dart';
import 'package:cnv/main.dart';

import 'account_test.dart' show FakeBackend;
import 'personal_test.dart' show MemoryPersonal;
import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

/// Android and FCM as the tests want them.
class FakePush implements PushBackend {
  bool granted = false;
  bool allow = true; // what the user answers to the permission question
  int asked = 0;
  String? currentToken = 'tok-1';
  final refresh = StreamController<String>.broadcast();
  final messages = StreamController<String>.broadcast();

  @override
  Future<bool> requestPermission() async {
    asked++;
    granted = granted || allow;
    return granted;
  }

  @override
  Future<bool> hasPermission() async => granted;

  @override
  Future<String?> token() async => currentToken;

  @override
  Stream<String> tokenRefresh() => refresh.stream;

  @override
  Stream<String> foreground() => messages.stream;
}

Future<void> settle() async {
  for (var i = 0; i < 5; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

Future<(AccountStore, NotificationStore)> signedIn(FakeBackend backend, FakePush push) async {
  final account = AccountStore(backend);
  final store = NotificationStore(account, backend, push, phoneId: () async => 'telefono-prova');
  await account.signInWithGoogle(); // "capo", admitted
  await settle();
  return (account, store);
}

void main() {
  test('off until turned on; turning them on asks the permission and registers the phone', () async {
    final backend = FakeBackend(), push = FakePush();
    final (_, store) = await signedIn(backend, push);
    expect(store.mode, 'off');
    expect(store.ready, isTrue);
    expect(push.asked, 0);

    await store.setMode('v');
    expect(push.asked, 1);
    expect(store.mode, 'v');
    expect(backend.notify['capo'], 'v');
    expect(backend.phones['capo'], {'telefono-prova': 'tok-1'});

    await store.setMode('off');
    expect(backend.notify['capo'], 'off');
    expect(backend.phones['capo'], isEmpty);
  });

  test('permission refused: the choice stays off, with a message', () async {
    final backend = FakeBackend(), push = FakePush()..allow = false;
    final (_, store) = await signedIn(backend, push);
    await store.setMode('all');
    expect(store.mode, 'off');
    expect(store.problem, contains('permesso'));
    expect(backend.phones['capo'], isNull);
    expect(backend.notify['capo'], isNull);
  });

  test('signed in again: the saved choice comes back and the phone is registered without asking', () async {
    final backend = FakeBackend()..notify['capo'] = 'all';
    final push = FakePush()..granted = true;
    final (_, store) = await signedIn(backend, push);
    expect(store.mode, 'all');
    expect(push.asked, 0);
    expect(backend.phones['capo'], {'telefono-prova': 'tok-1'});
  });

  test('a new token is saved; signing out removes the phone but keeps the choice', () async {
    final backend = FakeBackend(), push = FakePush();
    final (account, store) = await signedIn(backend, push);
    await store.setMode('all');
    push.refresh.add('tok-2');
    await settle();
    expect(backend.phones['capo'], {'telefono-prova': 'tok-2'});

    await account.signOut();
    await settle();
    expect(backend.phones['capo'], isEmpty);
    expect(backend.notify['capo'], 'all');
    expect(store.mode, 'off');
    expect(store.ready, isFalse);
  });

  test('not admitted: nothing to choose', () async {
    final backend = FakeBackend()
      ..accounts['estraneo@example.com'] = 'password'
      ..verifiedEmails.add('estraneo@example.com');
    final account = AccountStore(backend);
    final store = NotificationStore(account, backend, FakePush(), phoneId: () async => 'telefono-prova');
    await account.signInWithEmail('estraneo@example.com', 'password');
    await settle();
    expect(store.ready, isFalse);
    await store.setMode('all');
    expect(backend.notify, isEmpty);
  });

  testWidgets('the Notifiche choice in the Account box, and a notification with the app open', (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.6;
    addTearDown(tester.view.reset);
    final backend = FakeBackend(), push = FakePush();
    final account = AccountStore(backend);
    await tester.pumpWidget(CnvApp(
      store: await storeWith(LoadResult(sample(), offline: false)),
      personal: MemoryPersonal(),
      account: account,
      notifications: NotificationStore(account, backend, push, phoneId: () async => 'telefono-prova'),
      foreground: push.messages.stream,
    ));
    await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Voti')));
    await tester.pumpAndSettle();
    expect(find.text('Notifiche'), findsNothing); // not signed in

    await tester.tap(find.text('Accedi con Google'));
    await tester.pumpAndSettle();
    expect(find.text('Notifiche'), findsOneWidget);
    await tester.tap(find.text('Solo i miei V'));
    await tester.pumpAndSettle();
    expect(backend.notify['capo'], 'v');
    expect(backend.phones['capo'], {'telefono-prova': 'tok-1'});

    push.messages.add('🎬 In sala: Hope\nHope');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('🎬 In sala: Hope\nHope'), findsOneWidget);
  });
}
