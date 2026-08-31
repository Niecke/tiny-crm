import '../core/money_text.dart';

/// The pipeline, in order.
///
/// One enum rather than a stage plus a separate won/lost flag: two fields
/// describing the same thing drift apart, and then "is this open?" has two
/// answers.
///
/// Winning is not the end of it — an engagement billed per day worked *starts*
/// when it is won — so [running] and [completed] sit after [won]. Without them
/// every long engagement would leave the board the day the work began.
enum DealStage {
  lead('lead', 'Lead'),
  qualified('qualified', 'Qualified'),
  proposal('proposal', 'Proposal'),
  negotiation('negotiation', 'Negotiation'),
  won('won', 'Won'),
  running('running', 'Running'),
  completed('completed', 'Completed'),
  lost('lost', 'Lost');

  const DealStage(this.wire, this.label);

  /// The value the API uses. Kept separate from [label] so renaming what the
  /// operator reads never changes what is stored.
  final String wire;
  final String label;

  /// Still being competed for.
  bool get isOpen => switch (this) {
        DealStage.lead || DealStage.qualified || DealStage.proposal || DealStage.negotiation => true,
        _ => false,
      };

  /// Came off, whatever state the work is in.
  bool get isWon => switch (this) {
        DealStage.won || DealStage.running || DealStage.completed => true,
        _ => false,
      };

  /// Still belongs on the board: not completed, not lost.
  bool get isActive => isOpen || this == DealStage.won || this == DealStage.running;

  /// Unknown stages fall back to `lead` rather than throwing: a backend that
  /// learns a new stage must not blank the whole screen on an older build.
  static DealStage fromWire(String? value) => DealStage.values.firstWhere(
        (stage) => stage.wire == value,
        orElse: () => DealStage.lead,
      );
}

/// The coarse question a list is asking, as opposed to one exact [DealStage].
///
/// [active] is the one that matters most: it keeps a won-and-running
/// engagement on the board instead of dropping it the day the work starts.
enum DealStatus {
  open('open', 'In play'),
  active('active', 'On my plate'),
  won('won', 'Won'),
  finished('finished', 'Finished');

  const DealStatus(this.wire, this.label);

  final String wire;
  final String label;
}

/// How a deal is priced.
///
/// A single value column cannot describe both a fixed-price bid and an
/// engagement billed by the day without forcing a lie in one direction or the
/// other — invent a total, or leave it empty and vanish from the pipeline.
enum DealValueType {
  fixed('fixed', 'Fixed price'),
  rateBased('rate_based', 'By rate'),
  retainer('retainer', 'Retainer');

  const DealValueType(this.wire, this.label);

  final String wire;
  final String label;

  static DealValueType fromWire(String? value) => DealValueType.values.firstWhere(
        (type) => type.wire == value,
        orElse: () => DealValueType.fixed,
      );
}

/// The unit a rate is charged in, and the unit a volume is estimated in.
enum RateUnit {
  hour('hour', 'hour', 'hours'),
  day('day', 'day', 'days'),
  week('week', 'week', 'weeks'),
  month('month', 'month', 'months');

  const RateUnit(this.wire, this.label, this.plural);

  final String wire;
  final String label;
  final String plural;

  static RateUnit? fromWire(String? value) {
    if (value == null) return null;
    for (final unit in RateUnit.values) {
      if (unit.wire == value) return unit;
    }
    return null;
  }
}

/// An opportunity: a conversation that might become money.
class Deal {
  const Deal({
    required this.id,
    required this.title,
    this.valueType = DealValueType.fixed,
    this.fixedValue,
    this.rate,
    this.rateUnit,
    this.estimatedVolume,
    this.volumeUnit,
    this.expectedValue,
    this.isOpenEnded = false,
    this.currency = 'EUR',
    this.stage = DealStage.lead,
    this.expectedCloseDate,
    this.probability,
    this.lostReason,
    this.closedAt,
    this.notes,
    this.contactId,
    this.contactName,
    this.organizationId,
    this.organizationName,
  });

  final String id;
  final String title;

  // --- What it is worth ---------------------------------------------------
  // Every amount is the exact decimal string the API sent — see [formatMoney]
  // for why none of these is ever a double.
  final DealValueType valueType;
  final String? fixedValue;
  final String? rate;
  final RateUnit? rateUnit;

  /// A planning figure, not a cap. Null means genuinely open-ended.
  final String? estimatedVolume;
  final RateUnit? volumeUnit;

  /// Derived by the database: the contract sum, or rate × estimated volume when
  /// the two units agree. **Null means no total can be derived — not zero.**
  final String? expectedValue;

  /// Rate-priced with no volume estimate. A pipeline total has to count these
  /// separately rather than adding them as nothing.
  final bool isOpenEnded;
  final String currency;

  // --- Where it stands ----------------------------------------------------
  final DealStage stage;

  /// The forecast. [closedAt] is when it was actually decided; both are kept so
  /// "did we call it right?" stays answerable.
  final DateTime? expectedCloseDate;
  final int? probability;

  /// Only ever set while [stage] is `lost`; the API clears it on a reopen.
  final String? lostReason;
  final DateTime? closedAt;
  final String? notes;

  final String? contactId;

  /// Denormalised by the API so a list row shows who the deal is with without
  /// a request per row.
  final String? contactName;
  final String? organizationId;
  final String? organizationName;

  bool get isOpen => stage.isOpen;
  bool get isWon => stage.isWon;
  bool get isActive => stage.isActive;

  /// "48,000.00 EUR", or null when no total can be derived.
  String? get formattedExpectedValue =>
      expectedValue == null ? null : formatMoney(expectedValue!, currency);

  /// "800.00 EUR/day", or null when the deal is not rate-priced.
  String? get formattedRate =>
      (rate == null || rateUnit == null) ? null : '${formatMoney(rate!, currency)}/${rateUnit!.label}';

  /// The one line a list row shows for what a deal is worth.
  ///
  /// An open-ended engagement shows its rate rather than nothing at all —
  /// blanking it would make a real deal look like an unpriced one.
  String? get valueSummary {
    final total = formattedExpectedValue;
    if (total != null) return total;
    final perUnit = formattedRate;
    if (perUnit != null) return isOpenEnded ? '$perUnit · open-ended' : perUnit;
    return null;
  }

  factory Deal.fromJson(Map<String, dynamic> json) {
    // Money arrives as a decimal string; a number is accepted too so a
    // hand-rolled payload or a future serialiser change cannot break the
    // screen.
    String? amount(String key) => json[key] == null ? null : '${json[key]}';

    return Deal(
      id: json['id'] as String,
      title: json['title'] as String,
      valueType: DealValueType.fromWire(json['value_type'] as String?),
      fixedValue: amount('fixed_value'),
      rate: amount('rate'),
      rateUnit: RateUnit.fromWire(json['rate_unit'] as String?),
      estimatedVolume: amount('estimated_volume'),
      volumeUnit: RateUnit.fromWire(json['volume_unit'] as String?),
      expectedValue: amount('expected_value'),
      isOpenEnded: json['is_open_ended'] as bool? ?? false,
      currency: json['currency'] as String? ?? 'EUR',
      stage: DealStage.fromWire(json['stage'] as String?),
      expectedCloseDate: json['expected_close_date'] == null
          ? null
          : DateTime.parse(json['expected_close_date'] as String),
      probability: json['probability'] as int?,
      lostReason: json['lost_reason'] as String?,
      closedAt: json['closed_at'] == null ? null : DateTime.parse(json['closed_at'] as String),
      notes: json['notes'] as String?,
      contactId: json['contact_id'] as String?,
      contactName: json['contact_name'] as String?,
      organizationId: json['organization_id'] as String?,
      organizationName: json['organization_name'] as String?,
    );
  }
}
