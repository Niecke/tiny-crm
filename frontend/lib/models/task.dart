import '../core/date_time_text.dart';

/// Backend accepts exactly these values for `recurrence_rule`
/// (see app/recurrence.py); null means the task happens once.
const recurrenceRules = ['daily', 'weekly', 'monthly', 'yearly'];

/// Plural nouns for a rule repeated every N steps, keyed as [recurrenceRules].
const recurrenceUnits = {
  'daily': 'days',
  'weekly': 'weeks',
  'monthly': 'months',
  'yearly': 'years',
};

class Task {
  const Task({
    required this.id,
    required this.title,
    this.description,
    this.dueDate,
    required this.priority,
    this.tags = const [],
    this.done = false,
    this.recurrenceRule,
    this.recurrenceInterval = 1,
    this.recurrenceUntil,
    this.recurrenceParentId,
    this.contactId,
    this.contactName,
    this.dealId,
    this.dealTitle,
    this.interactionId,
    this.interactionSubject,
    this.nextOccurrence,
  });

  final String id;
  final String title;
  final String? description;
  final DateTime? dueDate;
  final int priority;
  final List<String> tags;
  final bool done;

  /// One of [recurrenceRules], or null for a one-off task.
  final String? recurrenceRule;
  final int recurrenceInterval;

  /// Last date an occurrence may fall on; null repeats indefinitely.
  final DateTime? recurrenceUntil;

  /// The instance this one was created from, so a series can be walked back.
  final String? recurrenceParentId;

  // What the task is about. All three independent, all optional — a plain
  // to-do links to nothing. The names come denormalised from the API so a list
  // row needs no request per task.
  final String? contactId;
  final String? contactName;
  final String? dealId;
  final String? dealTitle;

  /// The touchpoint this task came out of — "send the deck we talked about".
  final String? interactionId;
  final String? interactionSubject;

  /// True when the task points at anything at all.
  bool get isLinked =>
      contactId != null || dealId != null || interactionId != null;

  /// "Maria · ACME work", or null for an unattached to-do. What a list row
  /// shows under the title so a follow-up says who it is about.
  String? get linkSummary {
    final parts = [?contactName, ?dealTitle, ?interactionSubject];
    return parts.isEmpty ? null : parts.join(' · ');
  }

  /// Only set on the response to the completion that created it — the server
  /// says whether a next instance actually happened, since the series may have
  /// ended at [recurrenceUntil].
  final Task? nextOccurrence;

  bool get isOverdue =>
      dueDate != null && dueDate!.isBefore(DateTime.now());

  bool get repeats => recurrenceRule != null;

  /// "Repeats monthly", "Repeats every 2 weeks until 2026-12-31", or null when
  /// the task does not repeat.
  String? get recurrenceLabel {
    final rule = recurrenceRule;
    if (rule == null) return null;
    final every = recurrenceInterval == 1
        ? rule
        : 'every $recurrenceInterval ${recurrenceUnits[rule] ?? rule}';
    final until = recurrenceUntil;
    return until == null
        ? 'Repeats $every'
        : 'Repeats $every until ${formatDay(until)}';
  }

  factory Task.fromJson(Map<String, dynamic> json) => Task(
        id: json['id'] as String,
        title: json['title'] as String,
        description: json['description'] as String?,
        dueDate: json['due_date'] == null
            ? null
            : DateTime.parse(json['due_date'] as String),
        priority: json['priority'] as int,
        tags: (json['tags'] as List<dynamic>?)?.cast<String>() ?? [],
        done: json['done'] as bool? ?? false,
        recurrenceRule: json['recurrence_rule'] as String?,
        recurrenceInterval: json['recurrence_interval'] as int? ?? 1,
        recurrenceUntil: json['recurrence_until'] == null
            ? null
            : DateTime.parse(json['recurrence_until'] as String),
        recurrenceParentId: json['recurrence_parent_id'] as String?,
        contactId: json['contact_id'] as String?,
        contactName: json['contact_name'] as String?,
        dealId: json['deal_id'] as String?,
        dealTitle: json['deal_title'] as String?,
        interactionId: json['interaction_id'] as String?,
        interactionSubject: json['interaction_subject'] as String?,
        nextOccurrence: json['next_occurrence'] == null
            ? null
            : Task.fromJson(json['next_occurrence'] as Map<String, dynamic>),
      );
}
