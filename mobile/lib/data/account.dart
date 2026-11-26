import 'dart:async';

import 'package:flutter/foundation.dart';

import 'personal.dart';

/// The signed-in account, as the app needs it.
@immutable
class AccountUser {
  const AccountUser({required this.uid, required this.email, required this.verified, this.name, this.google = false});

  final String uid;
  final String email;
  final bool verified; // e-mail confirmed (Google accounts always are)
  final String? name;
  final bool google;
}

/// What the account can do in CNV, as the Firestore rules say.
enum Admission { none, checking, admitted, notAdmitted, error }

/// A problem with words for the user.
class AccountError implements Exception {
  const AccountError(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Firebase behind an interface, so the tests can do without it.
abstract class AccountBackend {
  Stream<AccountUser?> userChanges();
  AccountUser? get current;
  Future<void> signInWithGoogle();
  Future<void> signInWithEmail(String email, String password);
  Future<void> register(String email, String password); // also sends the confirmation e-mail
  Future<void> sendPasswordReset(String email);
  Future<void> sendVerification();
  Future<AccountUser?> reload(); // the e-mail may have been confirmed meanwhile
  Future<void> signOut();

  /// Whether the rules let this account in (reading its own document).
  Future<bool> isAdmitted(String uid);

  /// The admitted e-mails; null when this account is not the administrator.
  Future<List<String>?> allowList();
  Future<void> saveAllowList(List<String> emails);

  /// The account copy of the votes of [uid].
  PersonalRemote personalRemote(String uid);

  /// Notifications: the account's choice (utenti/{uid}.notify) and its phones.
  Future<String?> notifyMode(String uid);
  Future<void> setNotifyMode(String uid, String mode);

  /// The "ultimi giorni" notice for the account's V films (utenti/{uid}.lastDays).
  Future<bool> lastDays(String uid);
  Future<void> setLastDays(String uid, bool on);
  Future<void> savePhone(String uid, String phone, String token);
  Future<void> removePhone(String uid, String phone);

  /// Deletes the account's data in Firestore (votes, phones) and the account itself.
  Future<void> deleteAccount();
}

/// The account part of the app: who is signed in and whether it is admitted.
/// Without a backend (Firebase not started, or in the tests) the account is not available
/// and CNV works as before.
class AccountStore extends ChangeNotifier {
  AccountStore(this._backend) {
    _sub = _backend?.userChanges().listen(_onUser);
  }

  final AccountBackend? _backend;
  StreamSubscription<AccountUser?>? _sub;

  bool get available => _backend != null;
  AccountUser? user;
  Admission admission = Admission.none;
  List<String>? allowed; // set only for the administrator
  bool busy = false;

  bool get isAdmin => allowed != null;

  /// Run before signing out, while still signed in (e.g. to unregister this phone).
  final beforeSignOut = <Future<void> Function()>[];

  /// Where the votes of [uid] are kept in the account (null without Firebase).
  PersonalRemote? remoteFor(String uid) => _backend?.personalRemote(uid);

  void _onUser(AccountUser? u) {
    final changed = u?.uid != user?.uid || u?.verified != user?.verified;
    user = u;
    if (u == null) {
      admission = Admission.none;
      allowed = null;
      notifyListeners();
    } else if (changed) {
      checkAdmission();
    } else {
      notifyListeners();
    }
  }

  /// Ask the rules whether this account is in, and whether it manages the list.
  Future<void> checkAdmission() async {
    final u = user, backend = _backend;
    if (u == null || backend == null) return;
    if (!u.verified) {
      admission = Admission.none; // first the e-mail must be confirmed
      allowed = null;
      notifyListeners();
      return;
    }
    admission = Admission.checking;
    notifyListeners();
    try {
      final ok = await backend.isAdmitted(u.uid);
      admission = ok ? Admission.admitted : Admission.notAdmitted;
      allowed = ok ? await backend.allowList() : null;
    } catch (err) {
      debugPrint('Ammissione non controllata: $err');
      admission = Admission.error;
    }
    notifyListeners();
  }

  /// Runs an account action, showing it as busy; errors come back with words for the user.
  Future<void> _run(Future<void> Function(AccountBackend backend) action) async {
    final backend = _backend;
    if (backend == null) throw const AccountError("L'accesso non è disponibile in questa versione.");
    busy = true;
    notifyListeners();
    try {
      await action(backend);
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> signInWithGoogle() => _run((b) => b.signInWithGoogle());
  Future<void> signInWithEmail(String email, String password) => _run((b) => b.signInWithEmail(email.trim(), password));
  Future<void> register(String email, String password) => _run((b) => b.register(email.trim(), password));
  Future<void> sendPasswordReset(String email) => _run((b) => b.sendPasswordReset(email.trim()));
  Future<void> sendVerification() => _run((b) => b.sendVerification());
  Future<void> signOut() => _run((b) async {
        for (final hook in [...beforeSignOut]) {
          await hook();
        }
        await b.signOut();
      });

  /// "Elimina l'account": its data in Firebase and the account; the votes on the phone stay.
  Future<void> deleteAccount() => _run((b) => b.deleteAccount());

  /// "Ho confermato": reads the account again; if the e-mail is now confirmed, checks the list.
  Future<bool> reloadVerified() async {
    var verified = false;
    await _run((b) async {
      final u = await b.reload();
      if (u != null) _onUser(u);
      verified = u?.verified ?? false;
    });
    return verified;
  }

  /// The administrator adds or removes e-mails (lower case, no repeats, sorted).
  Future<void> setAllowList(List<String> emails) async {
    final clean = {for (final e in emails) if (e.trim().isNotEmpty) e.trim().toLowerCase()}.toList()..sort();
    await _run((b) async {
      await b.saveAllowList(clean);
      allowed = clean;
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}

/// A plausible e-mail address (Firebase checks it for real).
bool looksLikeEmail(String text) => RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(text.trim());
