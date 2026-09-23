/// Where a capture stands.
///
/// One enum rather than a flag beside a reason — the same choice the API makes,
/// and for the same reason: two fields describing one state drift apart, and
/// then "is this still waiting?" has two answers.
enum CaptureStatus {
  isNew('new', 'Waiting'),
  converted('converted', 'Converted'),
  dismissed('dismissed', 'Dismissed');

  const CaptureStatus(this.wire, this.label);

  /// The value the API uses. Kept separate from [label] so renaming what the
  /// operator reads never changes what is stored.
  final String wire;
  final String label;

  /// Unknown values fall back rather than throwing: a backend that learns a new
  /// status must not blank the whole screen on an older build.
  static CaptureStatus fromWire(String? value) => CaptureStatus.values.firstWhere(
    (status) => status.wire == value,
    orElse: () => CaptureStatus.isNew,
  );
}

/// A name or a link, parked in seconds, to be worked later.
///
/// [raw] is what was actually typed, pasted or shared, and the API never
/// rewrites it. [name] and [url] are guesses pulled out of it — editable, and
/// occasionally wrong, which is exactly why [raw] is kept.
class Capture {
  const Capture({
    required this.id,
    required this.raw,
    this.name,
    this.url,
    this.note,
    this.source,
    this.status = CaptureStatus.isNew,
    this.triagedAt,
    this.contactId,
    this.dealId,
    this.contactName,
    this.dealTitle,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String raw;
  final String? name;
  final String? url;
  final String? note;
  final String? source;
  final CaptureStatus status;
  final DateTime? triagedAt;

  /// What it became. Both null while it is still waiting; [dealId] stays null
  /// when it was converted to a person without opening a lead.
  final String? contactId;
  final String? dealId;
  final String? contactName;
  final String? dealTitle;

  final DateTime createdAt;
  final DateTime updatedAt;

  /// What to call this in a list. Falls back to [raw] rather than to
  /// "Untitled": a capture always has something the operator recognises,
  /// because they typed it.
  String get displayName => (name != null && name!.isNotEmpty) ? name! : raw;

  /// Still waiting for a decision — what the inbox and the nav badge count.
  bool get isOpen => status == CaptureStatus.isNew;

  /// Whole days since it was captured. The number that turns "3 waiting" into
  /// either a healthy inbox or a broken habit.
  int get daysWaiting => DateTime.now().difference(createdAt).inDays;

  factory Capture.fromJson(Map<String, dynamic> json) {
    return Capture(
      id: json['id'] as String,
      raw: json['raw'] as String,
      name: json['name'] as String?,
      url: json['url'] as String?,
      note: json['note'] as String?,
      source: json['source'] as String?,
      status: CaptureStatus.fromWire(json['status'] as String?),
      triagedAt: json['triaged_at'] == null
          ? null
          : DateTime.parse(json['triaged_at'] as String).toLocal(),
      contactId: json['contact_id'] as String?,
      dealId: json['deal_id'] as String?,
      contactName: json['contact_name'] as String?,
      dealTitle: json['deal_title'] as String?,
      createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
      updatedAt: DateTime.parse(json['updated_at'] as String).toLocal(),
    );
  }
}

/// What the nav badge needs, without pulling a page of rows nobody renders.
class CaptureCount {
  const CaptureCount({required this.waiting, this.oldestDays});

  final int waiting;

  /// Null when nothing is waiting. The half that makes [waiting] mean
  /// something.
  final int? oldestDays;

  factory CaptureCount.fromJson(Map<String, dynamic> json) {
    return CaptureCount(
      waiting: json['new'] as int,
      oldestDays: json['oldest_days'] as int?,
    );
  }
}

/// Everything one worked capture produced, in the order the screen reports it.
///
/// All of it in one response so triage can advance to the next item without a
/// follow-up request.
class CaptureConvertResult {
  const CaptureConvertResult({
    required this.capture,
    required this.contactId,
    required this.contactName,
    this.dealId,
    this.dealTitle,
    this.interactionId,
  });

  final Capture capture;
  final String contactId;
  final String contactName;
  final String? dealId;
  final String? dealTitle;
  final String? interactionId;

  /// True when a lead was opened, as opposed to just filing the person.
  bool get openedDeal => dealId != null;

  /// True when the outreach was recorded alongside.
  bool get loggedOutreach => interactionId != null;

  factory CaptureConvertResult.fromJson(Map<String, dynamic> json) {
    final contact = json['contact'] as Map<String, dynamic>;
    final deal = json['deal'] as Map<String, dynamic>?;
    final interaction = json['interaction'] as Map<String, dynamic>?;
    return CaptureConvertResult(
      capture: Capture.fromJson(json['capture'] as Map<String, dynamic>),
      contactId: contact['id'] as String,
      contactName: contact['name'] as String,
      dealId: deal?['id'] as String?,
      dealTitle: deal?['title'] as String?,
      interactionId: interaction?['id'] as String?,
    );
  }
}
