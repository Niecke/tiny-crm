import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/task.dart';

Map<String, dynamic> _task(Map<String, dynamic> extra) => {
      'id': 't1',
      "title": "Check the ORF winners' job pages",
      'priority': 0,
      'tags': <String>[],
      'done': false,
      ...extra,
    };

void main() {
  test('a task without a rule does not repeat', () {
    final task = Task.fromJson(_task({}));

    expect(task.repeats, isFalse);
    expect(task.recurrenceLabel, isNull);
    expect(task.recurrenceInterval, 1);
    expect(task.nextOccurrence, isNull);
  });

  test('an interval of one reads as the plain cadence', () {
    final task = Task.fromJson(_task({'recurrence_rule': 'monthly'}));

    expect(task.repeats, isTrue);
    expect(task.recurrenceLabel, 'Repeats monthly');
  });

  test('a longer interval is spelled out with its unit', () {
    for (final (rule, interval, label) in [
      ('daily', 3, 'Repeats every 3 days'),
      ('weekly', 2, 'Repeats every 2 weeks'),
      ('monthly', 6, 'Repeats every 6 months'),
      ('yearly', 2, 'Repeats every 2 years'),
    ]) {
      final task = Task.fromJson(
        _task({'recurrence_rule': rule, 'recurrence_interval': interval}),
      );

      expect(task.recurrenceLabel, label);
    }
  });

  test('an end date is named in the label', () {
    final task = Task.fromJson(_task({
      'recurrence_rule': 'weekly',
      'recurrence_interval': 2,
      'recurrence_until': DateTime(2026, 12, 31, 23, 59).toUtc().toIso8601String(),
    }));

    expect(task.recurrenceLabel, 'Repeats every 2 weeks until 2026-12-31');
  });

  test('the instance a completion created comes back with the response', () {
    final completed = Task.fromJson(_task({
      'done': true,
      'recurrence_rule': 'monthly',
      'due_date': DateTime(2026, 3, 1, 23, 59).toUtc().toIso8601String(),
      'next_occurrence': _task({
        'id': 't2',
        'recurrence_rule': 'monthly',
        'recurrence_parent_id': 't1',
        'due_date': DateTime(2026, 4, 1, 23, 59).toUtc().toIso8601String(),
      }),
    }));

    final next = completed.nextOccurrence;
    expect(next, isNotNull);
    expect(next!.id, 't2');
    expect(next.done, isFalse);
    expect(next.recurrenceParentId, 't1');
    expect(next.dueDate!.toLocal(), DateTime(2026, 4, 1, 23, 59));
    // The completed instance keeps its own due date: it is the history entry.
    expect(completed.dueDate!.toLocal(), DateTime(2026, 3, 1, 23, 59));
  });
}
