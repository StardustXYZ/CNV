import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/personal.dart';
import 'package:cnv/data/storage.dart';
import 'package:cnv/data/storage_io.dart';

/// Votes kept in memory: nothing written on disk.
class MemoryPersonal extends PersonalStore {
  int saves = 0;

  @override
  Future<void> persist() async => saves++;
}

void main() {
  test('touching a vote sets it, touching it again removes it', () async {
    final p = MemoryPersonal();
    await p.toggleVote(1, 'V', today: '2026-11-14');
    expect(p.vote(1), 'V');
    await p.toggleVote(1, '?', today: '2026-11-14');
    expect(p.vote(1), '?');
    await p.toggleVote(1, '?', today: '2026-11-14');
    expect(p.vote(1), isNull);
    expect(p.saves, 3);
  });

  test('✓ records the day; the cinema comes later; another vote forgets both', () async {
    final p = MemoryPersonal();
    await p.toggleVote(1, 'S', today: '2026-11-14');
    expect(p.seen[1]!.date, '2026-11-14');
    expect(p.seen[1]!.cinema, isNull);
    await p.setSeen(1, cinema: 'garden');
    expect(p.seen[1]!.cinema, 'garden');
    p.diary[1] = '2026-11-15';
    await p.toggleVote(1, 'V', today: '2026-11-16');
    expect(p.seen, isEmpty);
    expect(p.diary, isEmpty);
    await p.setSeen(1, cinema: 'garden'); // not seen: nothing to change
    expect(p.seen, isEmpty);
  });

  test('votes of a merged duplicate move to the film that absorbed it, the strongest one wins', () async {
    final p = MemoryPersonal()
      ..votesById = {42: 'S', 7: '?', 1: 'V', 8: 'V'}
      ..seen = {42: const SeenInfo('2026-11-01', 'garden')};
    await p.applyMerges({42: 1, 8: 7});
    expect(p.votesById, {1: 'S', 7: 'V'});
    expect(p.seen[1]!.cinema, 'garden');
    final saves = p.saves;
    await p.applyMerges({42: 1}); // already done: nothing to save
    expect(p.saves, saves);
  });

  test('the copy of the web version is restored, without the old X votes', () async {
    const web = '{"votes":{"1":"V","2":"X","3":"S","4":"?","x":"V"},"exported":{"1":"2026-10-01"},'
        '"seen":{"3":{"date":"2026-11-02","cinema":"andromeda"}},"diary":{},"saved_at":"2026-11-10T10:00:00Z"}';
    expect(PersonalStore.votesIn(web), 3);
    final p = MemoryPersonal()..votesById = {9: 'V'};
    expect(await p.importJson(web), 3);
    expect(p.votesById, {1: 'V', 3: 'S', 4: '?'});
    expect(p.exported, {1: '2026-10-01'});
    expect(p.seen[3]!.cinema, 'andromeda');
  });

  test('a file that is not a copy is refused and changes nothing', () async {
    final p = MemoryPersonal()..votesById = {9: 'V'};
    expect(PersonalStore.votesIn('{"films":[]}'), -1);
    expect(PersonalStore.votesIn('not json'), -1);
    await expectLater(p.importJson('not json'), throwsFormatException);
    await expectLater(p.importJson('[1,2]'), throwsFormatException);
    expect(p.votesById, {9: 'V'});
  });

  test('the copy has the same shape as the web one and comes back the same', () async {
    final p = MemoryPersonal()
      ..votesById = {1: 'V', 3: 'S'}
      ..seen = {3: const SeenInfo('2026-11-02')}
      ..diary = {3: '2026-11-03'};
    final text = p.exportJson(savedAt: '2026-11-14T19:00:00Z');
    final j = jsonDecode(text) as Map;
    expect(j['votes'], {'1': 'V', '3': 'S'});
    expect(j['seen'], {'3': {'date': '2026-11-02', 'cinema': null}});
    expect(j['saved_at'], '2026-11-14T19:00:00Z');
    expect(jsonDecode(p.exportJson()).containsKey('saved_at'), isFalse);

    final back = MemoryPersonal();
    await back.importJson(text);
    expect(back.votesById, p.votesById);
    expect(back.diary, p.diary);
  });

  test('the votes are saved in a file and read back when the app opens again', () async {
    final dir = await Directory.systemTemp.createTemp('cnv-voti');
    addTearDown(() => dir.delete(recursive: true));
    final p = PersonalStore(storage: FileStorage(() async => dir));
    await p.toggleVote(5, 'V', today: '2026-11-14');
    final again = PersonalStore(storage: FileStorage(() async => dir));
    await again.load();
    expect(again.votesById, {5: 'V'});
  });

  test('the first time in the browser the old web version votes are taken over, once', () async {
    final storage = MemoryStorage();
    const old = '{"votes": {"3": "V", "7": "?", "9": "X"}, "seen": {}, "exported": {"3": "2026-11-01"}, "diary": {}}';
    var asked = 0;
    Future<String?> oldVotes() async {
      asked++;
      return old;
    }

    final first = PersonalStore(storage: storage, oldWebVotes: oldVotes);
    await first.load();
    expect(first.votesById, {3: 'V', 7: '?'}); // the old X is dropped
    expect(first.exported, {3: '2026-11-01'});
    expect(storage.texts.containsKey('personal.json'), isTrue); // saved in the new place

    // Later the new votes win: the old ones are not read again
    await first.toggleVote(7, '?', today: '2026-11-16'); // removes the ?
    final again = PersonalStore(storage: storage, oldWebVotes: oldVotes);
    await again.load();
    expect(again.votesById, {3: 'V'});
    expect(asked, 1);
  });

  test('on the phone, or with nothing to take over, it starts empty', () async {
    final p = PersonalStore(storage: MemoryStorage(), oldWebVotes: () async => null);
    await p.load();
    expect(p.votesById, isEmpty);
  });
}
