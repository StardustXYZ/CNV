import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'storage.dart';

/// Where the versions of the app are published: the Releases of the GitHub repository, with
/// tags "app-v1.2.3" and the APK attached.
const releasesUrl = 'https://api.github.com/repos/StardustXYZ/CNV/releases?per_page=20';
const releasesPage = 'https://github.com/StardustXYZ/CNV/releases';
const _tagPrefix = 'app-v';

/// A published version of the app.
@immutable
class AppRelease {
  const AppRelease({required this.version, required this.apkUrl, required this.page, this.notes = ''});

  final String version; // "1.2.3"
  final String apkUrl; // download of the APK
  final String page; // its page on GitHub
  final String notes;
}

/// "1.10.0" is newer than "1.9.2". Anything that is not a version counts as 0.
int compareVersions(String a, String b) {
  List<int> parts(String v) => [for (final p in v.split('+').first.split('.')) int.tryParse(p) ?? 0];
  final (x, y) = (parts(a), parts(b));
  for (var i = 0; i < 3; i++) {
    final d = (i < x.length ? x[i] : 0) - (i < y.length ? y[i] : 0);
    if (d != 0) return d.sign;
  }
  return 0;
}

/// The newest published version of the app in the answer of GitHub (drafts, pre-releases
/// and releases without an APK are skipped).
AppRelease? latestRelease(Object? json) {
  if (json is! List) return null;
  AppRelease? best;
  for (final r in json) {
    if (r is! Map || r['draft'] == true || r['prerelease'] == true) continue;
    final tag = r['tag_name'];
    if (tag is! String || !tag.startsWith(_tagPrefix)) continue;
    final assets = r['assets'];
    final apk = assets is List
        ? assets.whereType<Map>().where((a) => '${a['name']}'.toLowerCase().endsWith('.apk')).firstOrNull
        : null;
    final url = apk?['browser_download_url'];
    if (url is! String) continue;
    final release = AppRelease(
      version: tag.substring(_tagPrefix.length),
      apkUrl: url,
      page: r['html_url'] is String ? r['html_url'] as String : releasesPage,
      notes: r['body'] is String ? (r['body'] as String).trim() : '',
    );
    if (best == null || compareVersions(release.version, best.version) > 0) best = release;
  }
  return best;
}

/// Checks whether a newer version of the app is out, when the app opens and on request.
/// The notice can be closed: it comes back only for an even newer version.
class UpdateStore extends ChangeNotifier {
  UpdateStore({
    required this.currentVersion,
    this.build,
    http.Client? client,
    TextStorage? storage,
  })  : _client = client ?? http.Client(),
        _storage = storage ?? deviceStorage();

  static const _name = 'aggiornamento.txt'; // the version dismissed with "Non ora"
  final String currentVersion;
  final String? build; // the build number (1.1.0+16 is "16"); none in the tests
  final http.Client _client;
  final TextStorage _storage;

  /// "1.1.0 (16)" for the screen: the version with its build number.
  String get versionLabel => build == null || build!.isEmpty ? currentVersion : '$currentVersion ($build)';

  AppRelease? available; // newer than this one
  String? _dismissed;
  bool checking = false;
  String? problem;
  DateTime? checkedAt;

  /// The notice at the top of the app: a newer version that was not dismissed.
  bool get showNotice => available != null && available!.version != _dismissed;

  Future<void> check() async {
    if (checking) return;
    checking = true;
    problem = null;
    notifyListeners();
    try {
      _dismissed ??= (await _storage.read(_name))?.trim() ?? '';
      final resp = await _client
          .get(Uri.parse(releasesUrl), headers: {'Accept': 'application/vnd.github+json'})
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) throw http.ClientException('GitHub ha risposto ${resp.statusCode}');
      final latest = latestRelease(jsonDecode(resp.body));
      available = latest != null && compareVersions(latest.version, currentVersion) > 0 ? latest : null;
      checkedAt = DateTime.now();
    } catch (err) {
      debugPrint('Aggiornamenti non controllati: $err');
      problem = 'Non riesco a controllare se ci sono versioni nuove.';
    } finally {
      checking = false;
      notifyListeners();
    }
  }

  /// "Non ora": the notice goes away until an even newer version comes out.
  Future<void> dismiss() async {
    final version = available?.version;
    if (version == null) return;
    _dismissed = version;
    notifyListeners();
    try {
      await _storage.write(_name, version);
    } catch (err) {
      debugPrint('Scelta non salvata: $err');
    }
  }
}
