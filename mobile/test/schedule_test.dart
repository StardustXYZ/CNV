import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/models.dart';
import 'package:cnv/data/schedule.dart';

void main() {
  test('until 06:00 it is still the previous evening', () {
    expect(programmeDay(DateTime(2026, 11, 14, 5, 59)), '2026-11-13');
    expect(programmeDay(DateTime(2026, 11, 14, 6, 0)), '2026-11-14');
    expect(programmeDay(DateTime(2026, 12, 1, 0, 30)), '2026-11-30'); // across months
    expect(programmeDay(DateTime(2027, 1, 1, 1, 0)), '2026-12-31'); // and years
  });

  test('a show listed before 06:00 runs after midnight', () {
    expect(showStart('2026-11-14', '21:15'), DateTime(2026, 11, 14, 21, 15));
    expect(showStart('2026-11-14', '00:30'), DateTime(2026, 11, 15, 0, 30));
    expect(showStart('2026-12-31', '01:00'), DateTime(2027, 1, 1, 1, 0));
  });

  test('end = start + runtime + ads and trailers', () {
    const settings = DataSettings(showExtraMinutes: 10);
    const hope = Film(id: 1, title: 'Hope', status: 'in_sala', runtime: 157);
    expect(showEnd(DateTime(2026, 11, 14, 21, 15), hope, settings), DateTime(2026, 11, 15, 0, 2));
    expect(showEnd(DateTime(2026, 11, 14, 21, 15), const Film(id: 2, title: 'X', status: 'in_sala'), settings), isNull);
  });

  test('dates as strings', () {
    expect(addDays('2026-11-30', 1), '2026-12-01');
    expect(addDays('2026-03-01', -1), '2026-02-28');
    expect(isoDate(DateTime(2026, 1, 5)), '2026-01-05');
    expect(hhmm(DateTime(2026, 1, 5, 7, 3)), '07:03');
  });
}
