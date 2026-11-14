import 'package:firebase_messaging/firebase_messaging.dart';

import 'notifications.dart';

/// Firebase Cloud Messaging. The notifications sent by GitHub carry their title and text:
/// Android shows them by itself when the app is closed; with the app open they arrive here.
class FirebasePushBackend implements PushBackend {
  final _messaging = FirebaseMessaging.instance;

  static bool _allowed(NotificationSettings s) =>
      s.authorizationStatus == AuthorizationStatus.authorized || s.authorizationStatus == AuthorizationStatus.provisional;

  @override
  Future<bool> requestPermission() async => _allowed(await _messaging.requestPermission());

  @override
  Future<bool> hasPermission() async => _allowed(await _messaging.getNotificationSettings());

  // The classic messaging token: it is what the nightly job sends to (firebase-admin,
  // messaging.Message(token=...)). The newer "direct send" registration (register(),
  // onRegistered) would need the server side to change too.
  @override
  // ignore: deprecated_member_use
  Future<String?> token() => _messaging.getToken();

  @override
  // ignore: deprecated_member_use
  Stream<String> tokenRefresh() => _messaging.onTokenRefresh;

  @override
  Stream<String> foreground() => FirebaseMessaging.onMessage
      .map((m) => [m.notification?.title, m.notification?.body].whereType<String>().join('\n'))
      .where((text) => text.isNotEmpty);
}
