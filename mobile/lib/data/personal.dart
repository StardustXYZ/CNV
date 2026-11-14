import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:path_provider/path_provider.dart';

/// V: voglio vederlo, ?: indeciso, S: visto (shown as ✓). The same codes as the web version.
const votes = ['V', '?', 'S'];
const voteLabels = {'V': 'V', '?': '?', 'S': '✓'};
const voteTitles = {'V': 'Voglio vederlo', '?': 'Indeciso', 'S': 'Visto'};
const _priority = {'S': 3, 'V': 2, '?': 1}; // two merged copies keep the most interested vote
const _sections = ['votes', 'seen', 'exported', 'diary'];

typedef Sections = Map<String, Map<String, Object?>>;

/// When and where a film marked ✓ was seen.
class SeenInfo {
  const SeenInfo(this.date, [this.cinema]);

  final String? date; // "YYYY-MM-DD"; null only in old copies of the web version
  final String? cinema; // cinema slug, null when not given

  Map<String, dynamic> toJson() => {'date': date, 'cinema': cinema};

  static SeenInfo? fromJson(Object? j) {
    if (j is! Map) return null;
    final (date, cinema) = (j['date'], j['cinema']);
    return SeenInfo(date is String ? date : null, cinema is String ? cinema : null);
  }
}

/// One entry changed: [value] null means removed.
@immutable
class PersonalChange {
  const PersonalChange(this.section, this.key, this.value);

  final String section; // votes, seen, exported or diary
  final String key; // film code
  final Object? value;

  @override
  bool operator ==(Object other) =>
      other is PersonalChange && other.section == section && other.key == key && jsonEncode(other.value) == jsonEncode(value);

  @override
  int get hashCode => Object.hash(section, key, jsonEncode(value));

  @override
  String toString() => '$section.$key=$value';
}

/// What the account holds, as it arrives (with "pending" when changes made here have not
/// reached the server yet).
class RemoteSnapshot {
  const RemoteSnapshot(this.data, {this.pending = false});

  final Map<String, dynamic>? data; // null: the account has no votes yet
  final bool pending;
}

/// The account copy of the votes (Firestore utenti/{uid}), behind an interface for the tests.
abstract class PersonalRemote {
  Future<Map<String, dynamic>?> fetch(); // from the server; null when there is nothing yet
  Stream<RemoteSnapshot> watch();
  Future<void> send(List<PersonalChange> changes);
}

enum SyncState { off, connecting, connected, error }

/// The user's own data: votes, films seen, and what already went to Letterboxd. It is kept
/// on the phone (same shape as the "copia dei voti" of the web version, so that copy can be
/// restored here) and, with an admitted account, also in the account, entry by entry.
class PersonalStore extends ChangeNotifier {
  PersonalStore({Future<Directory> Function()? folder}) : _folder = folder ?? getApplicationSupportDirectory;

  final Future<Directory> Function() _folder;

  Map<int, String> votesById = {};
  Map<int, SeenInfo> seen = {};
  Map<int, String> exported = {}; // film -> day the watchlist CSV was imported on Letterboxd
  Map<int, String> diary = {}; // film -> day the diary CSV was imported on Letterboxd

  // The account link
  PersonalRemote? _remote;
  PersonalRemote? _lastRemote;
  StreamSubscription<RemoteSnapshot>? _watching;
  Sections _sent = {}; // what the account has, as far as we know
  SyncState sync = SyncState.off;
  bool pending = false; // changes made here not yet on the server
  String? syncError;

  String? vote(int film) => votesById[film];

  Future<File> _file() async => File('${(await _folder()).path}${Platform.pathSeparator}personal.json');

  Future<void> load() async {
    try {
      final file = await _file();
      if (await file.exists()) _read(jsonDecode(await file.readAsString()));
    } catch (err) {
      debugPrint('Voti non leggibili: $err');
    }
    notifyListeners();
  }

  Future<void> _save() async {
    notifyListeners();
    _sendChanges();
    await persist();
  }

  /// Writes the data on the phone (the tests replace it).
  @protected
  Future<void> persist() async {
    try {
      await (await _file()).writeAsString(exportJson(), flush: true);
    } catch (err) {
      debugPrint('Voti non salvati: $err');
    }
  }

  /// Touching the current vote again removes it. Marking ✓ records [today] (after midnight,
  /// last night) without a cinema yet; any other vote forgets the ✓ and its diary entry.
  Future<void> toggleVote(int film, String vote, {required String today}) async {
    if (votesById[film] == vote) {
      votesById.remove(film);
    } else {
      votesById[film] = vote;
    }
    if (votesById[film] == 'S') {
      seen[film] = SeenInfo(today);
    } else {
      seen.remove(film);
      diary.remove(film);
    }
    await _save();
  }

  /// Day and cinema of a film marked ✓ (nothing for the others).
  Future<void> setSeen(int film, {String? date, String? cinema, bool clearCinema = false}) async {
    if (votesById[film] != 'S') return;
    final old = seen[film];
    seen[film] = SeenInfo(date ?? old?.date, clearCinema ? null : (cinema ?? old?.cinema));
    await _save();
  }

  /// The watchlist file was imported on Letterboxd: these films stay out of the next one.
  Future<void> markExported(Iterable<int> films, String today) async {
    for (final f in films) {
      exported[f] = today;
    }
    await _save();
  }

  /// The diary file was imported on Letterboxd: these films stay out of the next one.
  Future<void> markDiary(Iterable<int> films, String today) async {
    for (final f in films) {
      diary[f] = today;
    }
    await _save();
  }

  /// "Esporta di nuovo": the film goes back in the next watchlist file.
  Future<void> exportAgain(int film) async {
    if (exported.remove(film) != null) await _save();
  }

  /// "Esporta di nuovo": the film goes back in the next diary file.
  Future<void> diaryAgain(int film) async {
    if (diary.remove(film) != null) await _save();
  }

  /// Votes given to a duplicate that the sync merged into another film move to that film.
  Future<void> applyMerges(Map<int, int> merged) async {
    var changed = false;
    // The film that absorbed the duplicate keeps its own date if it has one
    void move<T>(Map<int, T> map, int old, int target) {
      final value = map.remove(old);
      if (value == null) return;
      map.putIfAbsent(target, () => value);
      changed = true;
    }

    for (final e in merged.entries) {
      final (old, target) = (e.key, e.value);
      final v = votesById.remove(old);
      if (v != null) {
        if ((_priority[v] ?? 0) > (_priority[votesById[target]] ?? 0)) votesById[target] = v;
        changed = true;
      }
      move(seen, old, target);
      move(exported, old, target);
      move(diary, old, target);
    }
    if (changed) await _save();
  }

  /// The copy of the votes: the same shape as the web version's ("cnv-voti-….json").
  String exportJson({String? savedAt}) => const JsonEncoder.withIndent(' ').convert({
        ..._asSections(),
        'saved_at': ?savedAt,
      });

  /// Restore a copy (from this app or from the web version), replacing the current data
  /// (in the account too, when linked). Returns how many votes it had; throws
  /// [FormatException] if it is not a copy of the votes.
  Future<int> importJson(String text) async {
    final Object? j;
    try {
      j = jsonDecode(text);
    } on FormatException {
      throw const FormatException('Il file non è una copia dei voti.');
    }
    if (j is! Map || j['votes'] is! Map) throw const FormatException('Il file non è una copia dei voti.');
    _read(j);
    await _save();
    return votesById.length;
  }

  /// How many votes a copy has, before restoring it (for the confirmation).
  static int votesIn(String text) {
    try {
      final j = jsonDecode(text);
      if (j is Map && j['votes'] is Map) {
        return (j['votes'] as Map).entries.where((e) => int.tryParse('${e.key}') != null && votes.contains(e.value)).length;
      }
    } catch (_) {}
    return -1;
  }

  void _read(Object? j) {
    if (j is! Map) return;
    Map<int, T> ids<T>(Object? m, T? Function(Object?) value) => {
          if (m is Map)
            for (final e in m.entries)
              if (int.tryParse('${e.key}') case final id?)
                if (value(e.value) case final v?) id: v,
        };
    // Only V, ? and ✓: the old X ("non mi interessa") of the web version is dropped
    votesById = ids(j['votes'], (v) => v is String && votes.contains(v) ? v : null);
    exported = ids(j['exported'], (v) => v is String ? v : null);
    seen = ids(j['seen'], SeenInfo.fromJson);
    diary = ids(j['diary'], (v) => v is String ? v : null);
  }

  Sections _asSections() => {
        'votes': {for (final e in votesById.entries) '${e.key}': e.value},
        'exported': {for (final e in exported.entries) '${e.key}': e.value},
        'seen': {for (final e in seen.entries) '${e.key}': e.value.toJson()},
        'diary': {for (final e in diary.entries) '${e.key}': e.value},
      };

  /// The data as the store reads it ([j] is a copy or the account document).
  static Sections _sectionsOf(Object? j) {
    final store = PersonalStore().._read(j);
    final sections = store._asSections();
    store.dispose();
    return sections;
  }

  /// What changed from [before] to [after], entry by entry.
  static List<PersonalChange> diff(Sections before, Sections after) => [
        for (final s in _sections) ...[
          for (final e in (after[s] ?? const {}).entries)
            if (jsonEncode(before[s]?[e.key]) != jsonEncode(e.value)) PersonalChange(s, e.key, e.value),
          for (final k in (before[s] ?? const {}).keys)
            if (!(after[s] ?? const {}).containsKey(k)) PersonalChange(s, k, null),
        ],
      ];

  // ------------------------------------------------------------------ account link

  bool get linked => _remote != null;

  /// Links the votes to the account: those already in the account count, and the ones only
  /// on this phone are added to it (the first time, all of them). Then every change goes
  /// both ways.
  Future<void> connect(PersonalRemote remote) async {
    await disconnect();
    _lastRemote = remote;
    sync = SyncState.connecting;
    syncError = null;
    notifyListeners();
    try {
      final account = _sectionsOf(await remote.fetch());
      final local = _asSections();
      final merged = {for (final s in _sections) s: <String, Object?>{...?local[s], ...?account[s]}};
      // A ✓ taken from the phone does not survive if the account says otherwise
      merged['seen']!.removeWhere((k, _) => merged['votes']![k] != 'S');
      merged['diary']!.removeWhere((k, _) => merged['votes']![k] != 'S');
      _read(merged);
      _sent = account;
      _remote = remote;
      sync = SyncState.connected;
      await _save(); // the votes only on this phone go to the account
      // Only now: the first news from the account already includes what was just sent
      _watching = remote.watch().listen(_onRemote, onError: (Object err) {
        debugPrint('Voti dell’account non ricevuti: $err');
        sync = SyncState.error;
        syncError = 'L’account non risponde: forse non sei più nella lista.';
        notifyListeners();
      });
    } catch (err) {
      debugPrint('Voti non collegati all’account: $err');
      _remote = null;
      sync = SyncState.error;
      syncError = 'Non riesco a raggiungere l’account. Controlla la connessione e riprova.';
      notifyListeners();
    }
  }

  /// Tries the link again after an error.
  Future<void> reconnect() async {
    final remote = _lastRemote;
    if (remote != null) await connect(remote);
  }

  /// Signed out: the votes stay on this phone, no longer linked.
  Future<void> disconnect() async {
    await _watching?.cancel();
    _watching = null;
    _remote = null;
    _lastRemote = null;
    _sent = {};
    pending = false;
    if (sync != SyncState.off) {
      sync = SyncState.off;
      syncError = null;
      notifyListeners();
    }
  }

  void _onRemote(RemoteSnapshot snap) {
    pending = snap.pending;
    final data = snap.data;
    if (data != null) {
      final account = _sectionsOf(data);
      if (diff(_asSections(), account).isNotEmpty) {
        _read(data); // changed on another phone
        unawaited(persist());
      }
      _sent = account;
    }
    if (sync == SyncState.error) {
      sync = SyncState.connected;
      syncError = null;
    }
    notifyListeners();
  }

  void _sendChanges() {
    final remote = _remote;
    if (remote == null) return;
    final now = _asSections();
    final changes = diff(_sent, now);
    if (changes.isEmpty) return;
    _sent = now;
    pending = true;
    // Without connection Firestore keeps them and sends them later: no waiting here
    unawaited(remote.send(changes).catchError((Object err) {
      debugPrint('Voti non mandati all’account: $err');
      sync = SyncState.error;
      syncError = 'Le ultime modifiche non sono arrivate all’account.';
      notifyListeners();
    }));
  }

  @override
  void dispose() {
    _watching?.cancel();
    super.dispose();
  }
}

/// Gives the pages the user's data (and rebuilds them when it changes).
class PersonalScope extends InheritedNotifier<PersonalStore> {
  const PersonalScope({super.key, required PersonalStore store, required super.child}) : super(notifier: store);

  static PersonalStore of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<PersonalScope>()!.notifier!;
}
