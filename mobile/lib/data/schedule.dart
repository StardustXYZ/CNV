/// Cinema-day rules, the same as the web version (phone/app.js, app/services/schedule.py).
library;

import 'models.dart';

/// Shows listed before this hour run after midnight, as the night of the previous day.
const lateShowCutoff = '06:00';

String _two(int n) => n.toString().padLeft(2, '0');

String isoDate(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';
String hhmm(DateTime d) => '${_two(d.hour)}:${_two(d.minute)}';

DateTime parseDay(String iso) {
  final parts = iso.split('-').map(int.parse).toList();
  return DateTime(parts[0], parts[1], parts[2]);
}

String addDays(String iso, int days) {
  final d = parseDay(iso);
  return isoDate(DateTime(d.year, d.month, d.day + days));
}

/// The cinema day in progress: until 06:00 it is still the previous evening's programme.
String programmeDay(DateTime now) => hhmm(now).compareTo(lateShowCutoff) < 0 ? addDays(isoDate(now), -1) : isoDate(now);

/// Real start of a show listed under [day]: shows before 06:00 run after midnight.
DateTime showStart(String day, String time) {
  final d = parseDay(day);
  final parts = time.split(':').map(int.parse).toList();
  final late = time.compareTo(lateShowCutoff) < 0;
  return DateTime(d.year, d.month, d.day + (late ? 1 : 0), parts[0], parts[1]);
}

/// Estimated end: start + runtime + ads and trailers (null without runtime).
DateTime? showEnd(DateTime start, Film? film, DataSettings settings) {
  final runtime = film?.runtime;
  if (runtime == null || runtime <= 0) return null;
  return start.add(Duration(minutes: runtime + settings.showExtraMinutes));
}
