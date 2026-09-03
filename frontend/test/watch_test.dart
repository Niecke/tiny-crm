import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/paged_result.dart';
import 'package:frontend/models/watch.dart';

String _iso(Duration offset) => DateTime.now().toUtc().add(offset).toIso8601String();

Map<String, dynamic> _watch(Map<String, dynamic> extra) => {
      'id': 'w1',
      'name': 'TED tenders',
      'url': 'https://ted.europa.eu/search',
      'kind': 'tender_portal',
      'recurrence_rule': 'weekly',
      'recurrence_interval': 1,
      'next_due_at': _iso(const Duration(days: 3)),
      'active': true,
      ...extra,
    };

void main() {
  group('Watch.fromJson', () {
    test('parses a full source', () {
      final watch = Watch.fromJson(_watch({
        'query_note': 'CPV 72000, Wien + NÖ',
        'notes': 'Login required.',
        'organization_id': 'o1',
        'organization_name': 'Stadt Wien',
        'last_checked_at': _iso(const Duration(days: -4)),
        'found_count': 2,
        'check_count': 11,
      }));

      expect(watch.name, 'TED tenders');
      expect(watch.kind, WatchKind.tenderPortal);
      // The saved search in words — a query string is unreadable months later.
      expect(watch.queryNote, 'CPV 72000, Wien + NÖ');
      expect(watch.organizationName, 'Stadt Wien');
      expect(watch.foundCount, 2);
      expect(watch.checkCount, 11);
    });

    test('a job board needs no company', () {
      // The whole reason this is not columns on an organization.
      final watch = Watch.fromJson(_watch({'kind': 'job_board', 'name': 'karriere.at'}));

      expect(watch.kind, WatchKind.jobBoard);
      expect(watch.organizationId, isNull);
      expect(watch.organizationName, isNull);
    });

    test('a kind this build does not know falls back instead of throwing', () {
      final watch = Watch.fromJson(_watch({'kind': 'rss_feed'}));

      expect(watch.kind, WatchKind.other);
    });

    test('a page of sources keeps the total for the pagination bar', () {
      final page = PagedResult.fromJson(<String, dynamic>{
        'items': <dynamic>[_watch({'id': 'w1'}), _watch({'id': 'w2'})],
        'total': 7,
        'skip': 0,
        'limit': 2,
      }, Watch.fromJson);

      expect(page.items.length, 2);
      expect(page.hasNext, isTrue);
    });
  });

  group('due state', () {
    test('a source past its date is due', () {
      final watch = Watch.fromJson(_watch({
        'next_due_at': _iso(const Duration(days: -3)),
        'last_checked_at': _iso(const Duration(days: -10)),
      }));

      expect(watch.isDue, isTrue);
      expect(watch.daysOverdue, 3);
      expect(watch.dueLabel, '3 days overdue');
    });

    test('a source not yet due says when it is', () {
      final watch = Watch.fromJson(_watch({
        'last_checked_at': _iso(const Duration(days: -4)),
      }));

      expect(watch.isDue, isFalse);
      expect(watch.daysOverdue, 0);
      expect(watch.dueLabel, startsWith('Due '));
    });

    test('a never-swept source says so rather than showing a date', () {
      // It has no history at all — "due today" would imply it had been on a
      // cadence, which it has not.
      final watch = Watch.fromJson(_watch({'next_due_at': _iso(Duration.zero)}));

      expect(watch.neverChecked, isTrue);
      expect(watch.dueLabel, 'Never checked');
    });

    test('a paused source is never due, whatever its date says', () {
      final watch = Watch.fromJson(_watch({
        'active': false,
        'next_due_at': _iso(const Duration(days: -90)),
        'last_checked_at': _iso(const Duration(days: -120)),
      }));

      expect(watch.isDue, isFalse);
      expect(watch.daysOverdue, 0);
    });
  });

  group('cadence label', () {
    test('reads naturally at an interval of one', () {
      expect(Watch.fromJson(_watch({'recurrence_rule': 'weekly'})).cadenceLabel, 'Every week');
      expect(Watch.fromJson(_watch({'recurrence_rule': 'daily'})).cadenceLabel, 'Every day');
    });

    test('pluralises past one', () {
      final watch = Watch.fromJson(
        _watch({'recurrence_rule': 'monthly', 'recurrence_interval': 3}),
      );

      expect(watch.cadenceLabel, 'Every 3 months');
    });
  });

  group('WatchCheck', () {
    test('a sweep that found nothing still parses as a record', () {
      final check = WatchCheck.fromJson(<String, dynamic>{
        'id': 'c1',
        'watch_id': 'w1',
        'checked_at': _iso(const Duration(days: -1)),
        'outcome': 'nothing',
      });

      expect(check.found, isFalse);
      expect(check.outcome.label, 'Nothing found');
      expect(check.createdDealId, isNull);
    });

    test('a find keeps a link to what it became', () {
      final check = WatchCheck.fromJson(<String, dynamic>{
        'id': 'c2',
        'watch_id': 'w1',
        'checked_at': _iso(const Duration(days: -1)),
        'outcome': 'found',
        'note': 'IT-DL Rahmenvertrag',
        'created_deal_id': 'd1',
      });

      expect(check.found, isTrue);
      expect(check.createdDealId, 'd1');
    });

    test('the record of a find survives the deal being deleted', () {
      // SET NULL on the API side: the link goes, the sweep stays.
      final check = WatchCheck.fromJson(<String, dynamic>{
        'id': 'c3',
        'watch_id': 'w1',
        'checked_at': _iso(const Duration(days: -1)),
        'outcome': 'found',
        'note': 'Worth remembering',
        'created_deal_id': null,
      });

      expect(check.found, isTrue);
      expect(check.note, 'Worth remembering');
      expect(check.createdDealId, isNull);
    });

    test('the check result carries the watch it moved on', () {
      final result = WatchCheckResult.fromJson(<String, dynamic>{
        'check': <String, dynamic>{
          'id': 'c1',
          'watch_id': 'w1',
          'checked_at': _iso(Duration.zero),
          'outcome': 'nothing',
        },
        'watch': _watch({'last_checked_at': _iso(Duration.zero), 'check_count': 1}),
      });

      expect(result.check.watchId, 'w1');
      // Logging a sweep advances the cadence in the same call.
      expect(result.watch.isDue, isFalse);
      expect(result.watch.checkCount, 1);
    });
  });

  group('wire values', () {
    test('are what the API uses, not the labels', () {
      // Renaming what the operator reads must never change what is stored.
      expect(WatchKind.tenderPortal.wire, 'tender_portal');
      expect(WatchKind.careersPage.wire, 'careers_page');
      expect(WatchKind.fromWire('job_board'), WatchKind.jobBoard);
      expect(CheckOutcome.found.wire, 'found');
      expect(CheckOutcome.fromWire(null), CheckOutcome.nothing);
    });
  });
}
