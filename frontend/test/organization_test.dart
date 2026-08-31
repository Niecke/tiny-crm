import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/contact.dart';
import 'package:frontend/models/organization.dart';
import 'package:frontend/models/paged_result.dart';

void main() {
  test('parses a full organization', () {
    final organization = Organization.fromJson(<String, dynamic>{
      'id': 'a1',
      'name': 'ACME Corporation',
      'domain': 'acme.example',
      'email': 'office@acme.example',
      'phone': '+49 30 123456',
      'address': 'Hauptstraße 1, 10115 Berlin',
      'industry': 'Manufacturing',
      'notes': 'Pays on time.',
      'contact_count': 3,
      'created_at': '2026-08-25T09:00:00',
      'updated_at': '2026-08-25T09:00:00',
    });

    expect(organization.id, 'a1');
    expect(organization.name, 'ACME Corporation');
    expect(organization.domain, 'acme.example');
    // The shared mailbox and switchboard belong to the company, not a person.
    expect(organization.email, 'office@acme.example');
    expect(organization.phone, '+49 30 123456');
    expect(organization.industry, 'Manufacturing');
    expect(organization.contactCount, 3);
  });

  test('leaves optional fields null and defaults the contact count', () {
    final organization = Organization.fromJson(<String, dynamic>{
      'id': 'a2',
      'name': 'Sole Trader',
    });

    expect(organization.domain, isNull);
    expect(organization.email, isNull);
    expect(organization.phone, isNull);
    expect(organization.address, isNull);
    expect(organization.industry, isNull);
    expect(organization.notes, isNull);
    expect(organization.contactCount, 0);
  });

  test('a contact carries its organization id and the name to show', () {
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c1',
      'name': 'Ada Lovelace',
      'organization_id': 'a1',
      'organization_name': 'ACME Corporation',
      'tags': <dynamic>[],
    });

    expect(contact.organizationId, 'a1');
    expect(contact.organizationName, 'ACME Corporation');
  });

  test('an unaffiliated contact has neither', () {
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c2',
      'name': 'Freelancer',
      'organization_id': null,
      'organization_name': null,
      'tags': <dynamic>['vip'],
    });

    expect(contact.organizationId, isNull);
    expect(contact.organizationName, isNull);
    expect(contact.tags, ['vip']);
  });

  test('a page of organizations keeps the total for the pagination bar', () {
    final page = PagedResult.fromJson(<String, dynamic>{
      'items': <dynamic>[
        <String, dynamic>{'id': 'a1', 'name': 'ACME', 'contact_count': 2},
        <String, dynamic>{'id': 'a2', 'name': 'Globex', 'contact_count': 0},
      ],
      'total': 7,
      'skip': 0,
      'limit': 2,
    }, Organization.fromJson);

    expect(page.items.map((o) => o.name), ['ACME', 'Globex']);
    expect(page.total, 7);
    expect(page.hasNext, isTrue);
    expect(page.pageCount, 4);
  });
}
