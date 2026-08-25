import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/core/date_time_text.dart';

void main() {
  test('formats local time as YYYY-MM-DD HH:MM', () {
    expect(formatWhen(DateTime(2026, 8, 25, 9, 5)), '2026-08-25 09:05');
  });

  test('parses what it formats, with and without a time', () {
    expect(parseWhen('2026-08-25 14:30'), DateTime(2026, 8, 25, 14, 30));
    expect(parseWhen('2026-08-25'), DateTime(2026, 8, 25));
    expect(parseWhen('2026-8-5 9:30'), DateTime(2026, 8, 5, 9, 30));
    expect(parseWhen('  2026-08-25T14:30 '), DateTime(2026, 8, 25, 14, 30));
  });

  test('rejects junk and out-of-range values', () {
    for (final bad in [
      '',
      'tomorrow',
      '25.08.2026',
      '2026-13-01',
      '2026-02-31',
      '2026-08-25 25:00',
      '2026-08-25 14:70',
    ]) {
      expect(parseWhen(bad), isNull, reason: bad);
    }
  });
}
