import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/changelog.dart';
import 'package:cnv/data/storage.dart';

const entries = [
  ChangelogEntry('1.3.0', ['terza']),
  ChangelogEntry('1.2.0', ['seconda', 'seconda bis']),
  ChangelogEntry('1.1.0', ['prima']),
];

void main() {
  late MemoryStorage storage;

  setUp(() => storage = MemoryStorage());

  ChangelogStore store(String current) => ChangelogStore(currentVersion: current, storage: storage, entries: entries);

  test('on a first install nothing is shown and the version is saved', () async {
    expect(await store('1.2.0').unseen(), isEmpty);
    expect(storage.texts['novita.txt'], '1.2.0');
  });

  test('after an update it lists the novelties of every version in between', () async {
    storage.texts['novita.txt'] = '1.0.0';
    expect(await store('1.2.0').unseen(), ['seconda', 'seconda bis', 'prima']);
  });

  test('a version newer than the installed one is not shown', () async {
    storage.texts['novita.txt'] = '1.1.0';
    expect(await store('1.2.0').unseen(), ['seconda', 'seconda bis']);
  });

  test('nothing is shown when the version is the one already seen', () async {
    storage.texts['novita.txt'] = '1.2.0';
    expect(await store('1.2.0').unseen(), isEmpty);
  });

  test('markSeen saves the current version, so the novelties do not come back', () async {
    storage.texts['novita.txt'] = '1.0.0';
    final s = store('1.2.0');
    expect(await s.unseen(), isNotEmpty);
    await s.markSeen();
    expect(await s.unseen(), isEmpty);
  });

  test('an update with nothing to say counts as seen', () async {
    storage.texts['novita.txt'] = '1.3.0';
    expect(await store('1.3.1').unseen(), isEmpty);
    expect(storage.texts['novita.txt'], '1.3.1');
  });
}
