/// Timestamps are typed and shown as `YYYY-MM-DD HH:MM` (24h, local time)
/// everywhere in the UI, independent of the browser locale.
const whenPattern = 'YYYY-MM-DD HH:MM';

String formatWhen(DateTime dt) {
  final local = dt.toLocal();
  String two(int v) => v.toString().padLeft(2, '0');
  return '${local.year}-${two(local.month)}-${two(local.day)} '
      '${two(local.hour)}:${two(local.minute)}';
}

final _whenRegExp = RegExp(
  r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?$',
);

/// Parses what [formatWhen] prints; the time part may be left off (midnight).
/// Returns null when the text is not a usable local timestamp.
DateTime? parseWhen(String text) {
  final match = _whenRegExp.firstMatch(text.trim());
  if (match == null) return null;

  final year = int.parse(match.group(1)!);
  final month = int.parse(match.group(2)!);
  final day = int.parse(match.group(3)!);
  final hour = int.parse(match.group(4) ?? '0');
  final minute = int.parse(match.group(5) ?? '0');
  if (month < 1 || month > 12 || day < 1 || hour > 23 || minute > 59) {
    return null;
  }

  final parsed = DateTime(year, month, day, hour, minute);
  // DateTime rolls overflow over silently — 2026-02-31 becomes March 3rd.
  if (parsed.month != month || parsed.day != day) return null;
  return parsed;
}

/// Just the day, `YYYY-MM-DD`, for fields the UI never shows a time for.
String formatDay(DateTime dt) {
  final local = dt.toLocal();
  String two(int v) => v.toString().padLeft(2, '0');
  return '${local.year.toString().padLeft(4, '0')}-'
      '${two(local.month)}-${two(local.day)}';
}
