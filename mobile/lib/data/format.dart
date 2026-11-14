/// Days and dates in words, as in the web version (formatDay and longDate in phone/app.js).
library;

import 'schedule.dart';

const _weekdays = ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom'];
const _months = [
  'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
  'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre',
];

/// "oggi", "domani" or e.g. "lun 16/11".
String formatDay(String iso, String today) {
  if (iso == today) return 'oggi';
  if (iso == addDays(today, 1)) return 'domani';
  final d = parseDay(iso);
  return '${_weekdays[d.weekday - 1]} ${d.day}/${d.month}';
}

/// e.g. "16 novembre", with the year only when it is not the current one.
String longDate(String iso, String today) {
  final d = parseDay(iso);
  final text = '${d.day} ${_months[d.month - 1]}';
  return d.year == parseDay(today).year ? text : '$text ${d.year}';
}

/// e.g. "1h 55m", "2h", "45m".
String formatRuntime(int minutes) {
  final h = minutes ~/ 60, m = minutes % 60;
  if (h == 0) return '${m}m';
  return m == 0 ? '${h}h' : '${h}h ${m.toString().padLeft(2, '0')}m';
}

String capitalize(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
