import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/personal.dart';

import 'personal_test.dart' show MemoryPersonal;

/// Firestore in memory: one document per account, shared by the "phones" of the test.
class FakeCloud {
  final docs = <String, Map<String, dynamic>>{};
  final _watchers = <FakeRemote>[];
  bool offline = false;
  int sends = 0;

  static Map<String, dynamic> _copy(Map<String, dynamic> m) => jsonDecode(jsonEncode(m)) as Map<String, dynamic>;

  void _apply(String uid, List<PersonalChange> changes) {
    final doc = _copy(docs[uid] ?? {}); // plain JSON maps, as Firestore gives them
    docs[uid] = doc;
    for (final c in changes) {
      final section = (doc[c.section] ??= <String, dynamic>{}) as Map<String, dynamic>;
      if (c.value == null) {
        section.remove(c.key);
      } else {
        section[c.key] = c.value;
      }
    }
    doc['updated'] = 'adesso';
  }

  /// The connection is back: the waiting changes reach the server and every phone hears it.
  void goOnline() {
    offline = false;
    for (final w in [..._watchers]) {
      for (final changes in w._queued) {
        _apply(w.uid, changes);
      }
      w._queued.clear();
    }
    for (final w in [..._watchers]) {
      w._emit();
    }
  }
}

class FakeRemote implements PersonalRemote {
  FakeRemote(this.cloud, this.uid);

  final FakeCloud cloud;
  final String uid;
  final _queued = <List<PersonalChange>>[];
  StreamController<RemoteSnapshot>? _out;

  @override
  Future<Map<String, dynamic>?> fetch() async {
    if (cloud.offline) throw Exception('unavailable');
    final doc = cloud.docs[uid];
    return doc == null ? null : FakeCloud._copy(doc);
  }

  @override
  Stream<RemoteSnapshot> watch() {
    _out = StreamController<RemoteSnapshot>(onListen: _emit, onCancel: () => cloud._watchers.remove(this));
    cloud._watchers.add(this);
    return _out!.stream;
  }

  /// What this phone sees: the server copy plus its own changes still waiting.
  void _emit() {
    final base = cloud.docs[uid];
    if (base == null && _queued.isEmpty) return;
    final view = FakeCloud()..docs[uid] = FakeCloud._copy(base ?? {});
    for (final changes in _queued) {
      view._apply(uid, changes);
    }
    _out?.add(RemoteSnapshot(view.docs[uid], pending: _queued.isNotEmpty));
  }

  @override
  Future<void> send(List<PersonalChange> changes) async {
    cloud.sends++;
    if (cloud.offline) {
      _queued.add(changes);
      _emit();
      return;
    }
    cloud._apply(uid, changes);
    for (final w in [...cloud._watchers]) {
      if (w.uid == uid) w._emit();
    }
  }
}

Future<void> settle() => Future<void>.delayed(Duration.zero);

void main() {
  test('first link: the account is empty, all the votes of the phone go there', () async {
    final cloud = FakeCloud();
    final phone = MemoryPersonal()
      ..votesById = {1: 'V', 2: 'S'}
      ..seen = {2: const SeenInfo('2026-11-08', 'garden')};
    await phone.connect(FakeRemote(cloud, 'me'));
    await settle();
    expect(phone.sync, SyncState.connected);
    expect(phone.linked, isTrue);
    expect(cloud.docs['me']!['votes'], {'1': 'V', '2': 'S'});
    expect(cloud.docs['me']!['seen'], {'2': {'date': '2026-11-08', 'cinema': 'garden'}});
    expect(phone.pending, isFalse);
  });

  test('a new phone: the account wins, the votes only on the phone are added', () async {
    final cloud = FakeCloud()
      ..docs['me'] = {
        'votes': {'1': 'S', '3': '?'},
        'seen': {'1': {'date': '2026-11-01', 'cinema': null}},
      };
    final phone = MemoryPersonal()
      ..votesById = {1: 'V', 4: 'S'}
      ..seen = {4: const SeenInfo('2026-11-09')};
    await phone.connect(FakeRemote(cloud, 'me'));
    await settle();
    expect(phone.votesById, {1: 'S', 3: '?', 4: 'S'});
    expect(phone.seen[1]!.date, '2026-11-01');
    expect(cloud.docs['me']!['votes'], {'1': 'S', '3': '?', '4': 'S'});
    expect(cloud.docs['me']!['seen'], containsPair('4', {'date': '2026-11-09', 'cinema': null}));
  });

  test('a ✓ of the phone does not survive when the account has another vote for that film', () async {
    final cloud = FakeCloud()..docs['me'] = {'votes': {'1': 'V'}};
    final phone = MemoryPersonal()
      ..votesById = {1: 'S'}
      ..seen = {1: const SeenInfo('2026-11-09')}
      ..diary = {1: '2026-11-10'};
    await phone.connect(FakeRemote(cloud, 'me'));
    await settle();
    expect(phone.votesById, {1: 'V'});
    expect(phone.seen, isEmpty);
    expect(phone.diary, isEmpty);
    expect(cloud.docs['me']!.containsKey('seen'), isFalse); // nothing to send
  });

  test('every change goes to the account entry by entry, and comes back on the other phone', () async {
    final cloud = FakeCloud();
    final a = MemoryPersonal(), b = MemoryPersonal();
    await a.connect(FakeRemote(cloud, 'me'));
    await b.connect(FakeRemote(cloud, 'me'));
    await settle();

    await a.toggleVote(7, 'V', today: '2026-11-14');
    await settle();
    expect(cloud.docs['me']!['votes'], {'7': 'V'});
    expect(b.vote(7), 'V');

    await b.toggleVote(7, 'S', today: '2026-11-14');
    await b.setSeen(7, cinema: 'garden');
    await settle();
    expect(a.vote(7), 'S');
    expect(a.seen[7]!.cinema, 'garden');

    await a.toggleVote(7, 'S', today: '2026-11-14'); // removed
    await settle();
    expect(cloud.docs['me']!['votes'], isEmpty);
    expect(cloud.docs['me']!['seen'], isEmpty);
    expect(b.votesById, isEmpty);
    expect(b.seen, isEmpty);
  });

  test('two phones changing different films do not overwrite each other', () async {
    final cloud = FakeCloud();
    final a = MemoryPersonal(), b = MemoryPersonal();
    await a.connect(FakeRemote(cloud, 'me'));
    await b.connect(FakeRemote(cloud, 'me'));
    await settle();
    cloud.offline = true;
    await a.toggleVote(1, 'V', today: '2026-11-14');
    await b.toggleVote(2, '?', today: '2026-11-14');
    await settle();
    expect(a.pending, isTrue);
    cloud.goOnline();
    await settle();
    expect(cloud.docs['me']!['votes'], {'1': 'V', '2': '?'});
    expect(a.votesById, {1: 'V', 2: '?'});
    expect(b.votesById, {1: 'V', 2: '?'});
    expect(a.pending, isFalse);
  });

  test('restoring a copy replaces the account too; a merge only moves what changed', () async {
    final cloud = FakeCloud();
    final phone = MemoryPersonal()..votesById = {1: 'V', 2: '?'};
    await phone.connect(FakeRemote(cloud, 'me'));
    await settle();
    await phone.importJson('{"votes":{"5":"S"},"seen":{"5":{"date":"2026-11-02","cinema":null}}}');
    await settle();
    expect(cloud.docs['me']!['votes'], {'5': 'S'});

    final before = cloud.sends;
    await phone.applyMerges({5: 50});
    await settle();
    expect(cloud.sends, before + 1);
    expect(cloud.docs['me']!['votes'], {'50': 'S'});
    expect(cloud.docs['me']!['seen'], {'50': {'date': '2026-11-02', 'cinema': null}});
  });

  test('signed out: changes stay on the phone; no connection at the start: an error to retry', () async {
    final cloud = FakeCloud();
    final phone = MemoryPersonal();
    await phone.connect(FakeRemote(cloud, 'me'));
    await phone.disconnect();
    expect(phone.sync, SyncState.off);
    await phone.toggleVote(3, 'V', today: '2026-11-14');
    await settle();
    expect(cloud.docs['me'], isNull);

    cloud.offline = true;
    await phone.connect(FakeRemote(cloud, 'me'));
    expect(phone.sync, SyncState.error);
    expect(phone.syncError, contains('connessione'));
    cloud.offline = false;
    await phone.reconnect();
    await settle();
    expect(phone.sync, SyncState.connected);
    expect(cloud.docs['me']!['votes'], {'3': 'V'});
  });

  test('changes are computed entry by entry', () {
    final changes = PersonalStore.diff(
      {'votes': {'1': 'V', '2': '?'}, 'seen': {'3': {'date': 'a', 'cinema': null}}},
      {'votes': {'1': 'V', '2': 'S'}, 'seen': {'3': {'date': 'a', 'cinema': 'x'}}, 'diary': {'3': 'd'}},
    );
    expect(changes, [
      const PersonalChange('votes', '2', 'S'),
      const PersonalChange('seen', '3', {'date': 'a', 'cinema': 'x'}),
      const PersonalChange('diary', '3', 'd'),
    ]);
    expect(PersonalStore.diff({'votes': {'1': 'V'}}, {'votes': {}}), [const PersonalChange('votes', '1', null)]);
  });
}
