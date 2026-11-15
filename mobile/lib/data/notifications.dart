import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'account.dart';

/// Which notifications the account wants: every film new in theaters, only its V ones, none.
const notifyModes = ['all', 'v', 'off'];
const notifyLabels = {'all': 'Tutti i film nuovi', 'v': 'Solo i miei V', 'off': 'Nessuna'};

/// Firebase Cloud Messaging behind an interface, so the tests can do without it.
abstract class PushBackend {
  Future<bool> requestPermission(); // asks Android (13+) the first time
  Future<bool> hasPermission();
  Future<String?> token();
  Stream<String> tokenRefresh();
  Stream<String> foreground(); // the text of a notification arrived with the app open
}

/// The notifications of the signed-in account: the choice is kept in the account
/// (utenti/{uid}.notify) and this phone is registered there (utenti/{uid}/telefoni), so
/// the nightly job of GitHub knows where to send them. Off until the user turns them on.
class NotificationStore extends ChangeNotifier {
  NotificationStore(this.account, this._backend, this._push, {Future<String> Function()? phoneId})
      : _phoneId = phoneId ?? _savedPhoneId {
    account.addListener(_update);
    account.beforeSignOut.add(_forgetPhone);
    _refresh = _push.tokenRefresh().listen(_onToken);
    _update();
  }

  final AccountStore account;
  final AccountBackend _backend;
  final PushBackend _push;
  final Future<String> Function() _phoneId;
  StreamSubscription<String>? _refresh;
  String? _uid;

  String mode = 'off';
  bool loading = false;
  bool busy = false;
  String? problem;

  bool get ready => _uid != null && !loading;

  void _update() {
    final user = account.user;
    final uid = user != null && account.admission == Admission.admitted ? user.uid : null;
    if (uid == _uid) return;
    _uid = uid;
    mode = 'off';
    problem = null;
    if (uid != null) unawaited(_load(uid));
    notifyListeners();
  }

  Future<void> _load(String uid) async {
    loading = true;
    notifyListeners();
    try {
      final saved = await _backend.notifyMode(uid);
      if (_uid != uid) return;
      mode = notifyModes.contains(saved) ? saved! : 'off';
      if (mode != 'off') {
        if (await _push.hasPermission()) {
          await _register(uid); // back on this phone (or a new token): registered again, without asking
        } else {
          // A new phone, or the app installed again: Android has to give the permission first
          mode = 'off';
          problem = 'Su questo telefono le notifiche non sono ancora attive: scegli di nuovo quali vuoi.';
        }
      }
    } catch (err) {
      debugPrint('Notifiche non lette: $err');
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> _register(String uid) async {
    final token = await _push.token();
    if (token == null || token.isEmpty) throw const AccountError('Il telefono non ha dato il codice per le notifiche.');
    await _backend.savePhone(uid, await _phoneId(), token);
  }

  /// The user's choice: turning them on asks Android for the permission.
  Future<void> setMode(String value) async {
    final uid = _uid;
    if (uid == null || !notifyModes.contains(value) || value == mode) return;
    busy = true;
    problem = null;
    notifyListeners();
    try {
      if (value == 'off') {
        await _backend.setNotifyMode(uid, 'off');
        await _backend.removePhone(uid, await _phoneId());
      } else {
        if (!await _push.requestPermission()) {
          problem = 'Android non ha dato il permesso: attiva le notifiche di CNV dalle impostazioni del telefono, poi riprova.';
          return;
        }
        await _register(uid);
        await _backend.setNotifyMode(uid, value);
      }
      mode = value;
    } on AccountError catch (err) {
      problem = err.message;
    } catch (err) {
      debugPrint('Notifiche non cambiate: $err');
      problem = 'Non riesco a salvare la scelta. Controlla la connessione e riprova.';
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  void _onToken(String token) {
    final uid = _uid;
    if (uid == null || mode == 'off') return;
    unawaited(_phoneId()
        .then((id) => _backend.savePhone(uid, id, token))
        .catchError((Object err) => debugPrint('Nuovo codice notifiche non salvato: $err')));
  }

  /// Before signing out: this phone stops getting the account's notifications (the choice
  /// stays in the account, for when it signs in again).
  Future<void> _forgetPhone() async {
    final uid = _uid;
    if (uid == null || mode == 'off') return;
    try {
      await _backend.removePhone(uid, await _phoneId());
    } catch (err) {
      debugPrint('Telefono non tolto: $err');
    }
  }

  /// A random name for this installation of the app, kept on the phone.
  static Future<String> _savedPhoneId() async {
    final file = File('${(await getApplicationSupportDirectory()).path}${Platform.pathSeparator}telefono.txt');
    if (await file.exists()) {
      final id = (await file.readAsString()).trim();
      if (RegExp(r'^[A-Za-z0-9_-]{8,64}$').hasMatch(id)) return id;
    }
    const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    final random = Random.secure();
    final id = List.generate(22, (_) => chars[random.nextInt(chars.length)]).join();
    await file.writeAsString(id, flush: true);
    return id;
  }

  @override
  void dispose() {
    account.removeListener(_update);
    account.beforeSignOut.remove(_forgetPhone);
    _refresh?.cancel();
    super.dispose();
  }
}
