import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/capture.dart';
import 'package:frontend/pages/capture_share_page.dart';

Map<String, dynamic> captureJson({Map<String, dynamic> overrides = const {}}) {
  return <String, dynamic>{
    'id': 'c1',
    'raw': 'Jane Doe https://linkedin.com/in/jane-doe',
    'name': 'Jane Doe',
    'url': 'https://linkedin.com/in/jane-doe',
    'note': null,
    'source': null,
    'status': 'new',
    'triaged_at': null,
    'contact_id': null,
    'deal_id': null,
    'contact_name': null,
    'deal_title': null,
    'created_at': '2026-09-01T09:00:00Z',
    'updated_at': '2026-09-01T09:00:00Z',
    ...overrides,
  };
}

void main() {
  group('Capture', () {
    test('a captured line round-trips with what was parsed out of it', () {
      final capture = Capture.fromJson(captureJson());

      expect(capture.id, 'c1');
      expect(capture.raw, 'Jane Doe https://linkedin.com/in/jane-doe');
      expect(capture.name, 'Jane Doe');
      expect(capture.url, 'https://linkedin.com/in/jane-doe');
      expect(capture.status, CaptureStatus.isNew);
      expect(capture.isOpen, isTrue);
    });

    test('a capture with no name falls back to what was typed', () {
      final capture = Capture.fromJson(
        captureJson(overrides: {'name': null, 'raw': 'https://example.com/team'}),
      );

      expect(capture.name, isNull);
      expect(capture.displayName, 'https://example.com/team');
    });

    test('an empty name is treated as no name', () {
      final capture = Capture.fromJson(captureJson(overrides: {'name': '', 'raw': 'fallback'}));

      expect(capture.displayName, 'fallback');
    });

    test('an untriaged capture has nothing to point at', () {
      final capture = Capture.fromJson(captureJson());

      expect(capture.triagedAt, isNull);
      expect(capture.contactId, isNull);
      expect(capture.dealId, isNull);
      expect(capture.contactName, isNull);
    });

    test('a converted capture carries what it became', () {
      final capture = Capture.fromJson(
        captureJson(
          overrides: {
            'status': 'converted',
            'triaged_at': '2026-09-04T08:00:00Z',
            'contact_id': 'p1',
            'deal_id': 'd1',
            'contact_name': 'Jane Doe',
            'deal_title': 'Outreach – Jane Doe',
          },
        ),
      );

      expect(capture.status, CaptureStatus.converted);
      expect(capture.isOpen, isFalse);
      expect(capture.triagedAt, isNotNull);
      expect(capture.contactName, 'Jane Doe');
      expect(capture.dealTitle, 'Outreach – Jane Doe');
    });

    test('a person can be filed without a lead being opened', () {
      final capture = Capture.fromJson(
        captureJson(
          overrides: {'status': 'converted', 'contact_id': 'p1', 'contact_name': 'Jane Doe'},
        ),
      );

      expect(capture.contactId, 'p1');
      expect(capture.dealId, isNull);
    });

    test('a dismissed capture is no longer waiting', () {
      final capture = Capture.fromJson(captureJson(overrides: {'status': 'dismissed'}));

      expect(capture.status, CaptureStatus.dismissed);
      expect(capture.isOpen, isFalse);
    });

    test('an unknown status falls back rather than throwing', () {
      // An older build must not blank the screen because the API learned a new
      // status.
      expect(CaptureStatus.fromWire('archived'), CaptureStatus.isNew);
      expect(CaptureStatus.fromWire(null), CaptureStatus.isNew);
    });

    test('wire values are what the API uses, not the labels', () {
      expect(CaptureStatus.isNew.wire, 'new');
      expect(CaptureStatus.converted.wire, 'converted');
      expect(CaptureStatus.dismissed.wire, 'dismissed');
    });

    test('how long it has waited is counted in whole days', () {
      final capture = Capture.fromJson(
        captureJson(
          overrides: {
            'created_at': DateTime.now()
                .toUtc()
                .subtract(const Duration(days: 3, hours: 2))
                .toIso8601String(),
          },
        ),
      );

      expect(capture.daysWaiting, 3);
    });
  });

  group('CaptureCount', () {
    test('an empty inbox has no oldest', () {
      final count = CaptureCount.fromJson(<String, dynamic>{'new': 0, 'oldest_days': null});

      expect(count.waiting, 0);
      expect(count.oldestDays, isNull);
    });

    test('a backlog reports how long the oldest has sat there', () {
      final count = CaptureCount.fromJson(<String, dynamic>{'new': 7, 'oldest_days': 12});

      expect(count.waiting, 7);
      expect(count.oldestDays, 12);
    });
  });

  group('CaptureConvertResult', () {
    Map<String, dynamic> resultJson({
      Map<String, dynamic>? deal,
      Map<String, dynamic>? interaction,
    }) {
      return <String, dynamic>{
        'capture': captureJson(overrides: {'status': 'converted', 'contact_id': 'p1'}),
        'contact': <String, dynamic>{'id': 'p1', 'name': 'Jane Doe'},
        'deal': deal,
        'interaction': interaction,
      };
    }

    test('a full conversion reports the person, the lead and the message', () {
      final result = CaptureConvertResult.fromJson(
        resultJson(
          deal: <String, dynamic>{'id': 'd1', 'title': 'Outreach – Jane Doe'},
          interaction: <String, dynamic>{'id': 'i1'},
        ),
      );

      expect(result.contactId, 'p1');
      expect(result.contactName, 'Jane Doe');
      expect(result.dealId, 'd1');
      expect(result.dealTitle, 'Outreach – Jane Doe');
      expect(result.interactionId, 'i1');
      expect(result.openedDeal, isTrue);
      expect(result.loggedOutreach, isTrue);
      expect(result.capture.status, CaptureStatus.converted);
    });

    test('filing a person without a lead or a message parses too', () {
      final result = CaptureConvertResult.fromJson(resultJson());

      expect(result.contactId, 'p1');
      expect(result.dealId, isNull);
      expect(result.interactionId, isNull);
      expect(result.openedDeal, isFalse);
      expect(result.loggedOutreach, isFalse);
    });
  });

  group('the share sheet', () {
    // Android fills these inconsistently, so the composed line has to survive
    // every shape without a special case per app.
    test('Chrome sends a title and a url', () {
      expect(
        CaptureSharePage.composeRaw(title: 'Jane Doe | LinkedIn', url: 'https://x.com/jane'),
        'Jane Doe | LinkedIn https://x.com/jane',
      );
    });

    test('some apps put the link in text and send nothing else', () {
      expect(
        CaptureSharePage.composeRaw(text: 'https://linkedin.com/in/jane-doe'),
        'https://linkedin.com/in/jane-doe',
      );
    });

    test('a url repeated across fields is not repeated in the line', () {
      expect(
        CaptureSharePage.composeRaw(
          title: 'Jane Doe',
          text: 'https://x.com/jane',
          url: 'https://x.com/jane',
        ),
        'Jane Doe https://x.com/jane',
      );
    });

    test('blank and missing fields are skipped', () {
      expect(CaptureSharePage.composeRaw(title: '  ', text: 'Jane Doe', url: null), 'Jane Doe');
    });

    test('sharing nothing composes nothing', () {
      expect(CaptureSharePage.composeRaw(), '');
      expect(CaptureSharePage.composeRaw(title: '', text: '  ', url: ''), '');
    });
  });
}
