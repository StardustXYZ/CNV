import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:cnv/data/repository.dart';

String json({String generatedAt = '2026-11-14T03:00+01:00', String title = 'Clayface'}) => jsonEncode({
      'generated_at': generatedAt,
      'cinemas': [],
      'films': [
        {'id': 1, 'title': title, 'status': 'in_sala'},
      ],
      'shows': [],
      'coming': [],
    });

void main() {
  late Directory folder;

  setUp(() async => folder = await Directory.systemTemp.createTemp('cnv_test_'));
  tearDown(() async => folder.delete(recursive: true));

  DataRepository repo(MockClient client) => DataRepository(client: client, folder: () async => folder);

  test('fresh data is used and saved for next time', () async {
    final result = await repo(MockClient((_) async => http.Response(json(), 200))).load();
    expect(result.offline, isFalse);
    expect(result.data.films.single.title, 'Clayface');
    expect(File('${folder.path}/data.json').existsSync(), isTrue);
  });

  test('without connection the saved copy is used', () async {
    await repo(MockClient((_) async => http.Response(json(title: 'Salvato'), 200))).load();
    final result = await repo(MockClient((_) async => throw const SocketException('offline'))).load();
    expect(result.offline, isTrue);
    expect(result.data.films.single.title, 'Salvato');
  });

  test('a broken answer does not replace the saved copy', () async {
    await repo(MockClient((_) async => http.Response(json(title: 'Buono'), 200))).load();
    final result = await repo(MockClient((_) async => http.Response('<html>errore</html>', 200))).load();
    expect(result.offline, isTrue);
    expect(result.data.films.single.title, 'Buono');
    final notFound = await repo(MockClient((_) async => http.Response('', 404))).load();
    expect(notFound.data.films.single.title, 'Buono');
  });

  test('no connection and no copy: an error', () async {
    expect(repo(MockClient((_) async => throw const SocketException('offline'))).load(), throwsA(isA<SocketException>()));
  });

  test('the store shows the saved copy at once, then the fresh data, and says when it is old', () async {
    await repo(MockClient((_) async => http.Response(json(title: 'Ieri'), 200))).load();
    final store = DataStore(
      repo(MockClient((_) async => http.Response(json(title: 'Oggi', generatedAt: '2026-11-14T03:00+01:00'), 200))),
      clock: () => DateTime.utc(2026, 11, 14, 10),
    );
    final seen = <String>[];
    store.addListener(() => seen.add(store.data?.films.single.title ?? '-'));
    await store.start();
    expect(seen.first, 'Ieri');
    expect(store.data!.films.single.title, 'Oggi');
    expect(store.state, LoadState.ready);
    expect(store.offline, isFalse);
    expect(store.stale, isFalse);

    final later = DataStore(
      repo(MockClient((_) async => http.Response(json(generatedAt: '2026-11-14T03:00+01:00'), 200))),
      clock: () => DateTime.utc(2026, 11, 15, 12),
    );
    await later.refresh();
    expect(later.stale, isTrue); // more than 30 hours after the data was made
  });

  test('the store reports the error only when there is nothing to show', () async {
    final store = DataStore(repo(MockClient((_) async => throw const SocketException('offline'))));
    await store.start();
    expect(store.state, LoadState.error);
  });
}
