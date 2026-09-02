// Backend accepts exactly these values for `kind` (see schemas/interaction.py).
const interactionKinds = ['call', 'meeting', 'email', 'note', 'other'];

class Interaction {
  const Interaction({
    required this.id,
    required this.kind,
    required this.subject,
    this.notes,
    required this.occurredAt,
    this.durationMinutes,
    this.done = false,
    this.tags = const [],
    this.contactIds = const [],
    this.organizationIds = const [],
    this.dealIds = const [],
    this.projectIds = const [],
  });

  final String id;
  final String kind;
  final String subject;
  final String? notes;

  /// Past = logged activity, future = planned mail or meeting.
  final DateTime occurredAt;
  final int? durationMinutes;
  final bool done;
  final List<String> tags;

  // What the interaction was about. Contacts used to be the only link, so
  // "every call about this deal" had no answer. A kickoff call is with people,
  // about a deal, under a project — all three at once.
  final List<String> contactIds;
  final List<String> organizationIds;
  final List<String> dealIds;
  final List<String> projectIds;

  /// How many records this interaction is attached to, all kinds together.
  int get linkCount =>
      contactIds.length +
      organizationIds.length +
      dealIds.length +
      projectIds.length;

  bool get isPlanned => occurredAt.isAfter(DateTime.now());

  /// Planned, its time has passed, and it was never confirmed as happened.
  bool get isOverdue => !isPlanned && !done;

  factory Interaction.fromJson(Map<String, dynamic> json) => Interaction(
        id: json['id'] as String,
        kind: json['kind'] as String,
        subject: json['subject'] as String,
        notes: json['notes'] as String?,
        occurredAt: DateTime.parse(json['occurred_at'] as String),
        durationMinutes: json['duration_minutes'] as int?,
        done: json['done'] as bool? ?? false,
        tags: (json['tags'] as List<dynamic>?)?.cast<String>() ?? [],
        contactIds:
            (json['contact_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        organizationIds:
            (json['organization_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        dealIds: (json['deal_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        projectIds:
            (json['project_ids'] as List<dynamic>?)?.cast<String>() ?? [],
      );
}
