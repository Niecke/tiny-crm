import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/task.dart';

Map<String, dynamic> _task(Map<String, dynamic> extra) => {
      'id': 't1',
      'title': 'Call Maria back on Thursday',
      'priority': 0,
      'tags': <String>[],
      'done': false,
      ...extra,
    };

void main() {
  test('a plain to-do links to nothing', () {
    final task = Task.fromJson(_task({}));

    expect(task.contactId, isNull);
    expect(task.dealId, isNull);
    expect(task.interactionId, isNull);
    expect(task.isLinked, isFalse);
    expect(task.linkSummary, isNull);
  });

  test('a task carries what it is about, with the names to show', () {
    final task = Task.fromJson(_task({
      'contact_id': 'c1',
      'contact_name': 'Maria Rossi',
      'deal_id': 'd1',
      'deal_title': 'Website relaunch',
      'interaction_id': 'i1',
      'interaction_subject': 'Kickoff call',
    }));

    expect(task.contactId, 'c1');
    expect(task.dealId, 'd1');
    expect(task.interactionId, 'i1');
    expect(task.isLinked, isTrue);
    // Denormalised by the API so a list row needs no request per task.
    expect(task.contactName, 'Maria Rossi');
    expect(task.linkSummary, 'Maria Rossi · Website relaunch · Kickoff call');
  });

  test('the three links are independent', () {
    final onlyDeal = Task.fromJson(_task({
      'deal_id': 'd1',
      'deal_title': 'Website relaunch',
    }));
    expect(onlyDeal.isLinked, isTrue);
    expect(onlyDeal.contactId, isNull);
    expect(onlyDeal.linkSummary, 'Website relaunch');

    final onlyContact = Task.fromJson(_task({
      'contact_id': 'c1',
      'contact_name': 'Maria',
    }));
    expect(onlyContact.dealId, isNull);
    expect(onlyContact.linkSummary, 'Maria');
  });

  test('a link whose record was deleted reads as unlinked', () {
    // ON DELETE SET NULL: the task survives, so the id and the name both come
    // back null rather than the row disappearing.
    final task = Task.fromJson(_task({
      'contact_id': null,
      'contact_name': null,
    }));

    expect(task.isLinked, isFalse);
    expect(task.linkSummary, isNull);
  });

  test('a spawned occurrence keeps the links of the one it came from', () {
    final completed = Task.fromJson(_task({
      'done': true,
      'contact_id': 'c1',
      'contact_name': 'Maria',
      'next_occurrence': _task({
        'id': 't2',
        'done': false,
        'contact_id': 'c1',
        'contact_name': 'Maria',
      }),
    }));

    expect(completed.nextOccurrence, isNotNull);
    // "Check in with Maria monthly" must stay about Maria.
    expect(completed.nextOccurrence!.contactId, 'c1');
    expect(completed.nextOccurrence!.contactName, 'Maria');
  });
}
