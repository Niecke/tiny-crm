import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/contact.dart';

void main() {
  test('parses every field a business files on a contact', () {
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c1',
      'name': 'Maria Rossi',
      'job_title': 'Head of Delivery',
      'email': 'maria@example.com',
      'email_secondary': 'm.rossi@private.example',
      'phone': '+43 1 234567',
      'phone_secondary': '+43 660 1234567',
      'website': 'https://rossi.example',
      'street': 'Hauptstraße 1',
      'postal_code': '1010',
      'city': 'Wien',
      'country': 'AT',
      'lifecycle_status': 'prospect',
      'relation_type': 'partner',
      'source': 'event',
      'preferred_language': 'de',
      'birthday': '1980-04-17',
      'known_day_rate': '850.00',
      'rate_currency': 'EUR',
      'works_with_freelancers': true,
      'tags': <dynamic>['vip'],
    });

    expect(contact.jobTitle, 'Head of Delivery');
    expect(contact.emailSecondary, 'm.rossi@private.example');
    expect(contact.phoneSecondary, '+43 660 1234567');
    expect(contact.website, 'https://rossi.example');
    expect(contact.street, 'Hauptstraße 1');
    expect(contact.postalCode, '1010');
    expect(contact.city, 'Wien');
    expect(contact.country, 'AT');
    expect(contact.lifecycleStatus, LifecycleStatus.prospect);
    expect(contact.relationType, RelationType.partner);
    expect(contact.source, ContactSource.event);
    expect(contact.preferredLanguage, 'de');
    expect(contact.birthday, DateTime(1980, 4, 17));
    // The exact decimal string the API sent — money never goes through a double.
    expect(contact.knownDayRate, '850.00');
    expect(contact.rateCurrency, 'EUR');
    expect(contact.worksWithFreelancers, isTrue);
  });

  test('a contact typed off a business card leaves the rest unset', () {
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c2',
      'name': 'Someone',
      'tags': <dynamic>[],
    });

    expect(contact.jobTitle, isNull);
    expect(contact.lifecycleStatus, isNull);
    expect(contact.relationType, isNull);
    expect(contact.source, isNull);
    expect(contact.birthday, isNull);
    expect(contact.postalAddress, isNull);
    expect(contact.formattedDayRate, isNull);
    // Not false: nobody has been asked.
    expect(contact.worksWithFreelancers, isNull);
    expect(contact.freelancerAnswer, FreelancerAnswer.unknown);
  });

  test('status and type are independent answers', () {
    // "Partner we have not approached yet" — the row that would be lost if the
    // two were ever collapsed into one field.
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c3',
      'name': 'Untouched partner',
      'relation_type': 'partner',
      'lifecycle_status': 'lead',
      'tags': <dynamic>[],
    });

    expect(contact.relationType, RelationType.partner);
    expect(contact.lifecycleStatus, LifecycleStatus.lead);
  });

  test('an unknown classification value reads as unset rather than throwing', () {
    // A backend that learns a new status must not blank the screen on an older
    // build; the column is nullable anyway.
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c4',
      'name': 'From the future',
      'lifecycle_status': 'churned',
      'relation_type': 'reseller',
      'source': 'carrier_pigeon',
      'tags': <dynamic>[],
    });

    expect(contact.lifecycleStatus, isNull);
    expect(contact.relationType, isNull);
    expect(contact.source, isNull);
  });

  test('the freelancer answer keeps all three states apart', () {
    expect(FreelancerAnswer.fromBool(true), FreelancerAnswer.yes);
    expect(FreelancerAnswer.fromBool(false), FreelancerAnswer.no);
    expect(FreelancerAnswer.fromBool(null), FreelancerAnswer.unknown);

    // And back out again, because null is what the API stores for "never asked".
    expect(FreelancerAnswer.yes.asBool, isTrue);
    expect(FreelancerAnswer.no.asBool, isFalse);
    expect(FreelancerAnswer.unknown.asBool, isNull);
  });

  test('the address reads as an envelope, with postcode and city on one line', () {
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c5',
      'name': 'Posted to',
      'street': 'Hauptstraße 1',
      'postal_code': '1010',
      'city': 'Wien',
      'country': 'AT',
      'tags': <dynamic>[],
    });

    expect(contact.postalAddress, 'Hauptstraße 1\n1010 Wien\nAT');
  });

  test('a half-filled address skips the lines it does not have', () {
    final contact = Contact.fromJson(<String, dynamic>{
      'id': 'c6',
      'name': 'City only',
      'city': 'Graz',
      'tags': <dynamic>[],
    });

    expect(contact.postalAddress, 'Graz');
  });

  test('the day rate is formatted with its currency, and only as a pair', () {
    final withRate = Contact.fromJson(<String, dynamic>{
      'id': 'c7',
      'name': 'Rated',
      'known_day_rate': '1250.5',
      'rate_currency': 'CHF',
      'tags': <dynamic>[],
    });
    final withoutCurrency = Contact.fromJson(<String, dynamic>{
      'id': 'c8',
      'name': 'Half a rate',
      'known_day_rate': '800.00',
      'tags': <dynamic>[],
    });

    expect(withRate.formattedDayRate, '1,250.50 CHF/day');
    // The API refuses this pairing, but a stale payload must not throw.
    expect(withoutCurrency.formattedDayRate, isNull);
  });
}
