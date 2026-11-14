import 'package:flutter_test/flutter_test.dart';

import 'package:cnv/data/format.dart';

void main() {
  test('days in words', () {
    expect(formatDay('2026-11-14', '2026-11-14'), 'oggi');
    expect(formatDay('2026-11-15', '2026-11-14'), 'domani');
    expect(formatDay('2026-11-16', '2026-11-14'), 'lun 16/11');
    expect(formatDay('2026-12-01', '2026-11-30'), 'domani'); // across months
  });

  test('long dates, with the year only when it changes', () {
    expect(longDate('2026-11-16', '2026-11-14'), '16 novembre');
    expect(longDate('2027-01-08', '2026-11-14'), '8 gennaio 2027');
  });

  test('runtime', () {
    expect([for (final m in [115, 120, 45, 61]) formatRuntime(m)], ['1h 55m', '2h', '45m', '1h 01m']);
  });
}
