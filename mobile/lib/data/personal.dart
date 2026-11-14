import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:path_provider/path_provider.dart';

/// V: voglio vederlo, ?: indeciso, S: visto (shown as ✓). The same codes as the web version.
const votes = ['V', '?', 'S'];
const voteLabels = {'V': 'V', '?': '?', 'S': '✓'};
const voteTitles = {'V': 'Voglio vederlo', '?': 'Indeciso', 'S': 'Visto'};
const _priority = {'S': 3, 'V': 2, '?': 1}; // two merged copies keep the most interested vote

/// When and where a film marked ✓ was seen.
class SeenInfo {
  const SeenInfo(this.date, [this.cinema]);

  final String date; // "YYYY-MM-DD"
  final String? cinema; // cinema slug, null when not given

  Map<String, dynamic> toJson() => {'date': date, 'cinema': cinema};

  static SeenInfo? fromJson(Object? j) {
    if (j is! Map) return null;
    final date = j['date'];
    if (date is! String) return null;
    final cinema = j['cinema'];
    return SeenInfo(date, cinema is String ? cinema : null);
  }
}

/// The user's own data, kept only on this phone (the account arrives in phase 6): votes,
/// films seen, and what already went to Letterboxd. The file has the same shape as the
/// "copia dei voti" of the web version, so that copy can be restored here.
class PersonalStore extends ChangeNotifier {
  PersonalStore({Future<Directory> Function()? folder}) : _folder = folder ?? getApplicationSupportDirectory;

  final Future<Directory> Function() _folder;

  Map<int, String> votesById = {};
  Map<int, SeenInfo> seen = {};
  Map<int, String> exported = {}; // film -> day the watchlist CSV was imported on Letterboxd
  Map<int, String> diary = {}; // film -> day the diary CSV was imported on Letterboxd

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

  Future<void> setSeen(int film, {String? date, String? cinema, bool clearCinema = false}) async {
    final old = seen[film];
    if (old == null) return;
    seen[film] = SeenInfo(date ?? old.date, clearCinema ? null : (cinema ?? old.cinema));
    await _save();
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
        'votes': {for (final e in votesById.entries) '${e.key}': e.value},
        'exported': {for (final e in exported.entries) '${e.key}': e.value},
        'seen': {for (final e in seen.entries) '${e.key}': e.value.toJson()},
        'diary': {for (final e in diary.entries) '${e.key}': e.value},
        'saved_at': ?savedAt,
      });

  /// Restore a copy (from this app or from the web version), replacing the current data.
  /// Returns how many votes it had; throws [FormatException] if it is not a copy of the votes.
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
}

/// Gives the pages the user's data (and rebuilds them when it changes).
class PersonalScope extends InheritedNotifier<PersonalStore> {
  const PersonalScope({super.key, required PersonalStore store, required super.child}) : super(notifier: store);

  static PersonalStore of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<PersonalScope>()!.notifier!;
}
