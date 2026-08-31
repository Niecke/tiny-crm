/// Money is carried as the exact decimal *string* the API sent, never parsed
/// into a double.
///
/// The backend stores `Numeric(14, 2)` and Pydantic serialises it as a string
/// on purpose: a binary double cannot hold 0.10, so a value that round-trips
/// through one comes back subtly wrong, and a pipeline total stops matching the
/// invoices it is meant to predict. Nothing in the UI does arithmetic on a
/// deal's value, so keeping it a string costs nothing and loses nothing.
///
/// Formatted locale-independently, like [formatWhen] does for timestamps:
/// grouped thousands, a dot for the decimal, the currency code after it.
String formatMoney(String amount, String currency) {
  final trimmed = amount.trim();
  final match = RegExp(r'^(-?)(\d+)(?:\.(\d*))?$').firstMatch(trimmed);
  // Not something we recognise — show it verbatim rather than mangling it.
  if (match == null) return '$trimmed $currency';

  final sign = match.group(1)!;
  final whole = match.group(2)!;
  // The API always sends 2 decimal places; pad anyway so a hand-written value
  // does not render as "5.5".
  final fraction = (match.group(3) ?? '').padRight(2, '0');

  final grouped = StringBuffer();
  for (var i = 0; i < whole.length; i++) {
    if (i > 0 && (whole.length - i) % 3 == 0) grouped.write(',');
    grouped.write(whole[i]);
  }

  return '$sign$grouped.$fraction $currency';
}
