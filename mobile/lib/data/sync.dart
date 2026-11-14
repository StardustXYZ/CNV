import 'account.dart';
import 'personal.dart';

/// Links the votes to the account while it is signed in and admitted, and unlinks them when
/// it signs out (the votes stay on the phone).
class VoteSync {
  VoteSync(this.account, this.personal) {
    account.addListener(_update);
    _update();
  }

  final AccountStore account;
  final PersonalStore personal;
  String? _linkedUid;

  void _update() {
    final user = account.user;
    final wanted = user != null && account.admission == Admission.admitted ? user.uid : null;
    // A failed check (no connection) does not unlink: the votes keep waiting for the account
    if (user != null && wanted == null && account.admission != Admission.notAdmitted) return;
    if (wanted == _linkedUid) return;
    _linkedUid = wanted;
    final remote = wanted == null ? null : account.remoteFor(wanted);
    if (remote == null) {
      personal.disconnect();
    } else {
      personal.connect(remote);
    }
  }

  void dispose() => account.removeListener(_update);
}
