import '../core/date_time_text.dart';
import 'task.dart' show recurrenceUnits;

/// What kind of source this is.
///
/// The two that matter most are **not** companies: a job board with a saved
/// search and a tender portal are sources you sweep, not parties you have a
/// relationship with. A careers page is the special case where the source does
/// have an organization behind it.
enum WatchKind {
  jobBoard('job_board', 'Job board', 'Job boards'),
  careersPage('careers_page', 'Careers page', 'Careers pages'),
  tenderPortal('tender_portal', 'Tender portal', 'Tender portals'),
  other('other', 'Other', 'Other');

  const WatchKind(this.wire, this.label, this.plural);

  /// The value the API uses. Kept separate from [label] so renaming what the
  /// operator reads never changes what is stored.
  final String wire;
  final String label;
  final String plural;

  /// Unknown kinds fall back rather than throwing: a backend that learns a new
  /// kind must not blank the whole screen on an older build.
  static WatchKind fromWire(String? value) => WatchKind.values.firstWhere(
        (kind) => kind.wire == value,
        orElse: () => WatchKind.other,
      );
}

/// What a sweep turned up. "nothing" is the normal, valuable answer.
enum CheckOutcome {
  nothing('nothing', 'Nothing found'),
  found('found', 'Found something');

  const CheckOutcome(this.wire, this.label);

  final String wire;
  final String label;

  static CheckOutcome fromWire(String? value) => CheckOutcome.values.firstWhere(
        (outcome) => outcome.wire == value,
        orElse: () => CheckOutcome.nothing,
      );
}

/// A source swept on a cadence: a job board, a careers page, a tender portal.
class Watch {
  const Watch({
    required this.id,
    required this.name,
    required this.url,
    this.kind = WatchKind.other,
    this.queryNote,
    this.notes,
    this.organizationId,
    this.organizationName,
    required this.recurrenceRule,
    this.recurrenceInterval = 1,
    this.lastCheckedAt,
    required this.nextDueAt,
    this.active = true,
    this.foundCount = 0,
    this.checkCount = 0,
  });

  final String id;
  final String name;
  final String url;
  final WatchKind kind;

  /// The saved search in words: keywords, CPV codes, region. A query string is
  /// unreadable six months later.
  final String? queryNote;
  final String? notes;

  final String? organizationId;

  /// Denormalised by the API so a list row shows the company without a request
  /// per row.
  final String? organizationName;

  /// One of [recurrenceRules] — the same closed set tasks use.
  final String recurrenceRule;
  final int recurrenceInterval;

  final DateTime? lastCheckedAt;
  final DateTime nextDueAt;
  final bool active;

  /// How many sweeps ever turned something up. The question a single timestamp
  /// cannot answer: is this source worth keeping?
  final int foundCount;
  final int checkCount;

  /// Due now or overdue. A paused source is never due, whatever its date says.
  bool get isDue => active && !nextDueAt.isAfter(DateTime.now());

  /// Whole days past due; 0 when it is not overdue.
  int get daysOverdue {
    if (!isDue) return 0;
    return DateTime.now().difference(nextDueAt).inDays;
  }

  bool get neverChecked => lastCheckedAt == null;

  /// "Every week", "Every 2 months".
  String get cadenceLabel => recurrenceInterval == 1
      ? 'Every ${recurrenceUnitSingular[recurrenceRule] ?? recurrenceRule}'
      : 'Every $recurrenceInterval ${recurrenceUnits[recurrenceRule] ?? recurrenceRule}';

  /// "Never checked", "Due today", "3 days overdue", "Due 2026-09-20".
  String get dueLabel {
    if (neverChecked) return 'Never checked';
    if (!isDue) return 'Due ${formatDay(nextDueAt)}';
    final days = daysOverdue;
    if (days == 0) return 'Due today';
    return days == 1 ? '1 day overdue' : '$days days overdue';
  }

  factory Watch.fromJson(Map<String, dynamic> json) => Watch(
        id: json['id'] as String,
        name: json['name'] as String,
        url: json['url'] as String,
        kind: WatchKind.fromWire(json['kind'] as String?),
        queryNote: json['query_note'] as String?,
        notes: json['notes'] as String?,
        organizationId: json['organization_id'] as String?,
        organizationName: json['organization_name'] as String?,
        recurrenceRule: json['recurrence_rule'] as String? ?? 'weekly',
        recurrenceInterval: json['recurrence_interval'] as int? ?? 1,
        lastCheckedAt: json['last_checked_at'] == null
            ? null
            : DateTime.parse(json['last_checked_at'] as String),
        nextDueAt: DateTime.parse(json['next_due_at'] as String),
        active: json['active'] as bool? ?? true,
        foundCount: json['found_count'] as int? ?? 0,
        checkCount: json['check_count'] as int? ?? 0,
      );
}

/// The singular noun a cadence counts, keyed as `recurrenceRules`.
const recurrenceUnitSingular = {
  'daily': 'day',
  'weekly': 'week',
  'monthly': 'month',
  'yearly': 'year',
};

/// One sweep of one watch. Append-only — there is no edit.
class WatchCheck {
  const WatchCheck({
    required this.id,
    required this.watchId,
    required this.checkedAt,
    required this.outcome,
    this.note,
    this.createdDealId,
    this.createdTaskId,
  });

  final String id;
  final String watchId;
  final DateTime checkedAt;
  final CheckOutcome outcome;
  final String? note;

  /// What this find turned into, so the source of a win stays traceable. Null
  /// again once that deal or task is deleted — the record of finding it stays.
  final String? createdDealId;
  final String? createdTaskId;

  bool get found => outcome == CheckOutcome.found;

  factory WatchCheck.fromJson(Map<String, dynamic> json) => WatchCheck(
        id: json['id'] as String,
        watchId: json['watch_id'] as String,
        checkedAt: DateTime.parse(json['checked_at'] as String),
        outcome: CheckOutcome.fromWire(json['outcome'] as String?),
        note: json['note'] as String?,
        createdDealId: json['created_deal_id'] as String?,
        createdTaskId: json['created_task_id'] as String?,
      );
}

/// The response to logging a sweep: the check, plus the watch it moved on.
class WatchCheckResult {
  const WatchCheckResult({required this.check, required this.watch});

  final WatchCheck check;
  final Watch watch;

  factory WatchCheckResult.fromJson(Map<String, dynamic> json) => WatchCheckResult(
        check: WatchCheck.fromJson(json['check'] as Map<String, dynamic>),
        watch: Watch.fromJson(json['watch'] as Map<String, dynamic>),
      );
}
