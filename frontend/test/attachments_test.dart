import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/document.dart';
import 'package:frontend/models/interaction.dart';
import 'package:frontend/widgets/attachment_pickers.dart';

Map<String, dynamic> _document(Map<String, dynamic> extra) => {
      'id': 'd1',
      'title': 'Signed contract',
      'description': null,
      'tags': <String>[],
      'format': 'pdf',
      'size': 2048,
      'storage_key': 'k',
      'created_at': '2026-09-01T09:00:00',
      'updated_at': '2026-09-01T09:00:00',
      ...extra,
    };

Map<String, dynamic> _interaction(Map<String, dynamic> extra) => {
      'id': 'i1',
      'kind': 'call',
      'subject': 'Kickoff call',
      'occurred_at': '2026-09-01T09:00:00',
      ...extra,
    };

void main() {
  group('Document links', () {
    test('a document filed against every kind of record', () {
      final doc = Document.fromJson(_document({
        'contact_ids': <String>['c1'],
        'organization_ids': <String>['o1'],
        'deal_ids': <String>['de1'],
        'project_ids': <String>['p1'],
      }));

      expect(doc.contactIds, ['c1']);
      expect(doc.organizationIds, ['o1']);
      expect(doc.dealIds, ['de1']);
      expect(doc.projectIds, ['p1']);
      expect(doc.linkCount, 4);
    });

    test('an unfiled document has no links', () {
      final doc = Document.fromJson(_document({}));

      expect(doc.contactIds, isEmpty);
      expect(doc.organizationIds, isEmpty);
      expect(doc.dealIds, isEmpty);
      expect(doc.projectIds, isEmpty);
      expect(doc.linkCount, 0);
    });

    test('the same document sits under several records at once', () {
      // An NDA filed against both the person and their company.
      final doc = Document.fromJson(_document({
        'contact_ids': <String>['c1'],
        'organization_ids': <String>['o1'],
      }));

      expect(doc.linkCount, 2);
    });
  });

  group('Interaction links', () {
    test('an interaction records everything it was about', () {
      final interaction = Interaction.fromJson(_interaction({
        'contact_ids': <String>['c1', 'c2'],
        'organization_ids': <String>['o1'],
        'deal_ids': <String>['de1'],
        'project_ids': <String>['p1'],
      }));

      expect(interaction.contactIds, ['c1', 'c2']);
      expect(interaction.organizationIds, ['o1']);
      expect(interaction.dealIds, ['de1']);
      expect(interaction.projectIds, ['p1']);
      expect(interaction.linkCount, 5);
    });

    test('an interaction with no links still parses', () {
      final interaction = Interaction.fromJson(_interaction({}));

      expect(interaction.linkCount, 0);
      expect(interaction.dealIds, isEmpty);
    });

    test('an older payload without the new fields does not throw', () {
      // Defensive: a cached response from before this change must not take
      // the screen down.
      final interaction = Interaction.fromJson(_interaction({
        'contact_ids': <String>['c1'],
      }));

      expect(interaction.contactIds, ['c1']);
      expect(interaction.organizationIds, isEmpty);
    });
  });

  group('withInitial', () {
    test('adds the record the form was opened from', () {
      expect(withInitial(['c1'], 'c2'), ['c1', 'c2']);
    });

    test('does not duplicate one that is already linked', () {
      expect(withInitial(['c1', 'c2'], 'c1'), ['c1', 'c2']);
    });

    test('handles a new record with nothing linked yet', () {
      expect(withInitial(null, 'c1'), ['c1']);
      expect(withInitial(null, null), isEmpty);
    });
  });
}
