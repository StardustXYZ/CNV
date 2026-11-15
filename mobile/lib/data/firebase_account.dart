import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:google_sign_in/google_sign_in.dart';

import 'account.dart';
import 'personal.dart';

/// The account on Firebase: login with Google or e-mail and password, and the admission
/// as the Firestore rules decide it (firebase/firestore.rules).
class FirebaseAccountBackend implements AccountBackend {
  FirebaseAccountBackend() {
    _auth.setLanguageCode('it'); // confirmation and password e-mails in Italian
  }

  final _auth = FirebaseAuth.instance;
  final _db = FirebaseFirestore.instance;
  bool _googleReady = false;

  static AccountUser? _user(User? u) => u == null
      ? null
      : AccountUser(
          uid: u.uid,
          email: u.email ?? '',
          verified: u.emailVerified,
          name: u.displayName,
          google: u.providerData.any((p) => p.providerId == 'google.com'),
        );

  @override
  Stream<AccountUser?> userChanges() => _auth.userChanges().map(_user);

  @override
  AccountUser? get current => _user(_auth.currentUser);

  @override
  Future<void> signInWithGoogle() async {
    final google = GoogleSignIn.instance;
    try {
      if (!_googleReady) {
        await google.initialize(); // the web client comes from google-services.json
        _googleReady = true;
      }
      final account = await google.authenticate();
      final idToken = account.authentication.idToken;
      if (idToken == null) throw const AccountError('Google non ha dato il permesso di accesso. Riprova.');
      await _auth.signInWithCredential(GoogleAuthProvider.credential(idToken: idToken));
    } on GoogleSignInException catch (err) {
      if (err.code == GoogleSignInExceptionCode.canceled) return; // closed by the user
      throw AccountError('Accesso con Google non riuscito (${err.code.name}). Riprova.');
    } on FirebaseAuthException catch (err) {
      throw AccountError(_authMessage(err));
    }
  }

  @override
  Future<void> signInWithEmail(String email, String password) =>
      _guard(() => _auth.signInWithEmailAndPassword(email: email, password: password));

  @override
  Future<void> register(String email, String password) => _guard(() async {
        final cred = await _auth.createUserWithEmailAndPassword(email: email, password: password);
        await cred.user?.sendEmailVerification();
      });

  @override
  Future<void> sendPasswordReset(String email) => _guard(() => _auth.sendPasswordResetEmail(email: email));

  @override
  Future<void> sendVerification() => _guard(() async => _auth.currentUser?.sendEmailVerification());

  @override
  Future<AccountUser?> reload() async {
    final u = _auth.currentUser;
    if (u == null) return null;
    await _guard(() async {
      await u.reload();
      await _auth.currentUser?.getIdToken(true); // the rules see the confirmed e-mail only in a new token
    });
    return _user(_auth.currentUser);
  }

  @override
  Future<void> signOut() async {
    await _auth.signOut();
    if (_googleReady) await GoogleSignIn.instance.signOut();
  }

  @override
  Future<bool> isAdmitted(String uid) async {
    try {
      await _db.doc('utenti/$uid').get(const GetOptions(source: Source.server));
      return true;
    } on FirebaseException catch (err) {
      if (err.code == 'permission-denied') return false;
      rethrow;
    }
  }

  @override
  Future<List<String>?> allowList() async {
    try {
      final snap = await _db.doc('config/ammessi').get(const GetOptions(source: Source.server));
      final emails = snap.data()?['email'];
      return [for (final e in (emails is List ? emails : const [])) if (e is String) e];
    } on FirebaseException catch (err) {
      if (err.code == 'permission-denied') return null; // not the administrator
      rethrow;
    }
  }

  @override
  Future<void> saveAllowList(List<String> emails) async {
    try {
      await _db.doc('config/ammessi').update({'email': emails});
    } on FirebaseException catch (err) {
      throw AccountError(err.code == 'permission-denied'
          ? 'Solo l’amministratore può cambiare la lista.'
          : 'Lista non salvata (${err.code}). Controlla la connessione e riprova.');
    }
  }

  @override
  PersonalRemote personalRemote(String uid) => FirebasePersonalRemote(_db.doc('utenti/$uid'));

  @override
  Future<String?> notifyMode(String uid) async {
    final snap = await _db.doc('utenti/$uid').get();
    final mode = snap.data()?['notify'];
    return mode is String ? mode : null;
  }

  @override
  Future<void> setNotifyMode(String uid, String mode) =>
      _db.doc('utenti/$uid').set({'notify': mode}, SetOptions(merge: true));

  @override
  Future<void> savePhone(String uid, String phone, String token) =>
      _db.doc('utenti/$uid/telefoni/$phone').set({'token': token, 'updated': FieldValue.serverTimestamp()});

  @override
  Future<void> removePhone(String uid, String phone) => _db.doc('utenti/$uid/telefoni/$phone').delete();

  @override
  Future<void> deleteAccount() async {
    final user = _auth.currentUser;
    if (user == null) return;
    try {
      // The data first, while the rules still let this account in (not in the list: nothing to delete)
      final phones = await _db.collection('utenti/${user.uid}/telefoni').get();
      for (final phone in phones.docs) {
        await phone.reference.delete();
      }
      await _db.doc('utenti/${user.uid}').delete();
    } on FirebaseException catch (err) {
      if (err.code != 'permission-denied') {
        throw AccountError('Dati non cancellati (${err.code}). Controlla la connessione e riprova.');
      }
    }
    try {
      await user.delete();
    } on FirebaseAuthException catch (err) {
      if (err.code == 'requires-recent-login') {
        throw const AccountError('I dati sono cancellati; per eliminare anche l’account, per sicurezza esci, '
            'rientra e tocca subito di nuovo “Elimina l’account”.');
      }
      throw AccountError(_authMessage(err));
    }
    if (_googleReady) await GoogleSignIn.instance.signOut();
  }

  static Future<void> _guard(Future<void> Function() action) async {
    try {
      await action();
    } on FirebaseAuthException catch (err) {
      throw AccountError(_authMessage(err));
    }
  }

  static String _authMessage(FirebaseAuthException err) => switch (err.code) {
        'invalid-email' => 'L’indirizzo email non è valido.',
        'user-disabled' => 'Questo account è stato disattivato.',
        'user-not-found' || 'wrong-password' || 'invalid-credential' => 'Email o password sbagliate.',
        'email-already-in-use' => 'Esiste già un account con questa email: accedi, o recupera la password.',
        'weak-password' => 'La password è troppo debole: usane una di almeno 6 caratteri.',
        'too-many-requests' => 'Troppi tentativi: aspetta qualche minuto e riprova.',
        'network-request-failed' => 'Senza connessione: riprova quando sei online.',
        'account-exists-with-different-credential' =>
          'Questa email ha già un account con un altro modo di accesso: usa quello.',
        _ => 'Accesso non riuscito (${err.code}).',
      };
}

/// The votes in Firestore, utenti/{uid}: one document with the same maps as the copy of the
/// votes. Each change touches only its entry, so two phones changing different films do not
/// overwrite each other. Firestore keeps the changes made without connection and sends them
/// when it comes back.
class FirebasePersonalRemote implements PersonalRemote {
  FirebasePersonalRemote(this._doc);

  final DocumentReference<Map<String, dynamic>> _doc;

  @override
  Future<Map<String, dynamic>?> fetch() async {
    final snap = await _doc.get(const GetOptions(source: Source.server));
    return snap.exists ? snap.data() : null;
  }

  @override
  Stream<RemoteSnapshot> watch() => _doc
      .snapshots(includeMetadataChanges: true) // also when the server confirms what was sent
      .map((s) => RemoteSnapshot(s.exists ? s.data() : null, pending: s.metadata.hasPendingWrites));

  @override
  Future<void> send(List<PersonalChange> changes) {
    final data = <String, dynamic>{'updated': FieldValue.serverTimestamp()};
    for (final c in changes) {
      (data[c.section] ??= <String, dynamic>{})[c.key] = c.value ?? FieldValue.delete();
    }
    return _doc.set(data, SetOptions(merge: true));
  }
}
