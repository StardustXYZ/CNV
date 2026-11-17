import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:cnv/data/repository.dart';
import 'package:cnv/data/storage.dart';
import 'package:cnv/data/updates.dart';
import 'package:cnv/main.dart';
import 'package:cnv/pages/privacy_page.dart';

import 'personal_test.dart' show MemoryPersonal;
import 'programme_test.dart' show sample;
import 'widget_test.dart' show storeWith;

Map<String, dynamic> release(String tag, {bool apk = true, bool draft = false, bool pre = false}) => {
      'tag_name': tag,
      'draft': draft,
      'prerelease': pre,
      'html_url': 'https://github.com/StardustXYZ/CNV/releases/tag/$tag',
      'body': 'Novità di $tag',
      'assets': [
        if (apk) {'name': 'CNV-$tag.apk', 'browser_download_url': 'https://github.com/download/$tag.apk'},
        {'name': 'note.txt', 'browser_download_url': 'https://github.com/download/note.txt'},
      ],
    };

UpdateStore storeWith2(String current, List<Map<String, dynamic>> releases, TextStorage dismissed, {int status = 200}) =>
    UpdateStore(
      currentVersion: current,
      client: MockClient((_) async => http.Response(jsonEncode(releases), status)),
      storage: dismissed,
    );

void main() {
  late MemoryStorage dismissed; // where "Non ora" is kept, as the app's files

  setUp(() => dismissed = MemoryStorage());

  test('versions are compared number by number', () {
    expect(compareVersions('1.10.0', '1.9.2'), 1);
    expect(compareVersions('0.11.0', '0.11.0+11'), 0);
    expect(compareVersions('0.9', '0.10.0'), -1);
    expect(compareVersions('2', '1.99.99'), 1);
  });

  test('the newest app release with an APK; drafts, pre-releases and other tags are skipped', () {
    final latest = latestRelease([
      release('app-v0.12.0'),
      release('app-v0.14.0', draft: true),
      release('app-v0.13.0', pre: true),
      release('app-v0.12.5', apk: false),
      release('dati-2026-11-15'),
      release('app-v0.11.0'),
    ]);
    expect(latest!.version, '0.12.0');
    expect(latest.apkUrl, 'https://github.com/download/app-v0.12.0.apk');
    expect(latest.notes, 'Novità di app-v0.12.0');
    expect(latestRelease([]), isNull);
    expect(latestRelease({'message': 'Not Found'}), isNull);
  });

  test('a newer version is offered; "Non ora" hides it until an even newer one', () async {
    var store = storeWith2('0.11.0', [release('app-v0.12.0')], dismissed);
    await store.check();
    expect(store.available!.version, '0.12.0');
    expect(store.showNotice, isTrue);
    await store.dismiss();
    expect(store.showNotice, isFalse);
    expect(store.available, isNotNull); // still offered in the Voti page

    store = storeWith2('0.11.0', [release('app-v0.12.0')], dismissed); // the app opened again
    await store.check();
    expect(store.showNotice, isFalse);
    store = storeWith2('0.11.0', [release('app-v0.13.0')], dismissed);
    await store.check();
    expect(store.showNotice, isTrue);
  });

  test('already the latest, or GitHub not answering', () async {
    var store = storeWith2('0.12.0', [release('app-v0.12.0')], dismissed);
    await store.check();
    expect(store.available, isNull);
    expect(store.checkedAt, isNotNull);
    store = storeWith2('0.11.0', [], dismissed, status: 403);
    await store.check();
    expect(store.available, isNull);
    expect(store.problem, contains('versioni nuove'));
  });

  testWidgets('the notice at the top, the Voti page box and the privacy page', (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.6;
    addTearDown(tester.view.reset);
    final updates = storeWith2('0.11.0', [release('app-v0.12.0')], dismissed);
    await tester.pumpWidget(CnvApp(
      store: await storeWith(LoadResult(sample(), offline: false)),
      personal: MemoryPersonal(),
      updates: updates,
    ));
    await tester.runAsync(updates.check);
    await tester.pumpAndSettle();
    expect(find.text('È uscita la versione 0.12.0 di CNV'), findsOneWidget);

    await tester.tap(find.text('Non ora'));
    await tester.pumpAndSettle();
    expect(find.text('È uscita la versione 0.12.0 di CNV'), findsNothing);

    await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('Voti')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Privacy: quali dati usa CNV'));
    await tester.pumpAndSettle();
    expect(find.text('Hai la versione 0.11.0: è uscita la 0.12.0.'), findsOneWidget);
    expect(find.text('Scarica la versione 0.12.0'), findsOneWidget);

    await tester.tap(find.text('Privacy: quali dati usa CNV'));
    await tester.pumpAndSettle();
    expect(find.byType(PrivacyPage), findsOneWidget);
    expect(find.text('Chi vede i tuoi dati'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Cancellare i dati'), 300,
        scrollable: find.descendant(of: find.byType(PrivacyPage), matching: find.byType(Scrollable)));
    expect(find.text('Cancellare i dati'), findsOneWidget);
  });
}
