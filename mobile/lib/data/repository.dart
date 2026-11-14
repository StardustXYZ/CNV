import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'models.dart';

/// The data of the web version, rebuilt by GitHub every night.
const dataUrl = 'https://stardustxyz.github.io/CNV/data.json';

/// Older than this, the data is shown with a warning (the nightly update did not arrive).
const staleAfter = Duration(hours: 30);

class LoadResult {
  const LoadResult(this.data, {required this.offline});

  final CnvData data;
  final bool offline; // the copy kept on the phone, because the network did not answer
}

/// Downloads data.json and keeps the last good copy on the phone, for use without connection.
class DataRepository {
  DataRepository({http.Client? client, Future<Directory> Function()? folder, this.url = dataUrl})
      : _client = client ?? http.Client(),
        _folder = folder ?? getApplicationSupportDirectory;

  final http.Client _client;
  final Future<Directory> Function() _folder;
  final String url;

  Future<File> _cacheFile() async => File('${(await _folder()).path}${Platform.pathSeparator}data.json');

  /// Fresh data when the network answers (saved for next time), else the saved copy.
  /// Throws only when there is neither.
  Future<LoadResult> load() async {
    try {
      final resp = await _client.get(Uri.parse(url), headers: {'Cache-Control': 'no-cache'}).timeout(const Duration(seconds: 20));
      if (resp.statusCode != 200) throw HttpException('data.json: HTTP ${resp.statusCode}');
      final text = utf8.decode(resp.bodyBytes);
      final data = CnvData.fromJson(jsonDecode(text) as Map<String, dynamic>); // checked before replacing the copy
      await (await _cacheFile()).writeAsString(text, flush: true);
      return LoadResult(data, offline: false);
    } catch (err) {
      final saved = await readSaved();
      if (saved != null) return LoadResult(saved, offline: true);
      rethrow;
    }
  }

  /// The copy kept on the phone (null if there is none or it cannot be read).
  Future<CnvData?> readSaved() async {
    try {
      final file = await _cacheFile();
      if (!await file.exists()) return null;
      return CnvData.fromJson(jsonDecode(await file.readAsString()) as Map<String, dynamic>);
    } catch (err) {
      debugPrint('Copia dei dati non leggibile: $err');
      return null;
    }
  }
}

enum LoadState { loading, ready, error }

/// What the pages show: the data, whether it is the saved copy, and whether it is old.
class DataStore extends ChangeNotifier {
  DataStore(this._repository, {DateTime Function()? clock}) : _clock = clock ?? DateTime.now;

  final DataRepository _repository;
  final DateTime Function() _clock;

  LoadState state = LoadState.loading;
  CnvData? data;
  bool offline = false;
  bool refreshing = false;

  DateTime get now => _clock();

  /// The nightly update did not arrive: the shows may have changed.
  bool get stale => data != null && now.difference(data!.generatedAt) > staleAfter;

  /// At start: the saved copy at once, then the fresh data.
  Future<void> start() async {
    final saved = await _repository.readSaved();
    if (saved != null && data == null) {
      data = saved;
      state = LoadState.ready;
      notifyListeners();
    }
    await refresh();
  }

  Future<void> refresh() async {
    refreshing = true;
    notifyListeners();
    try {
      final result = await _repository.load();
      data = result.data;
      offline = result.offline;
      state = LoadState.ready;
    } catch (err) {
      debugPrint('Dati non scaricati: $err');
      if (data == null) {
        state = LoadState.error;
      } else {
        offline = true;
      }
    } finally {
      refreshing = false;
      notifyListeners();
    }
  }
}
