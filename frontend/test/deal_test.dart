import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/core/money_text.dart';
import 'package:frontend/models/deal.dart';
import 'package:frontend/models/paged_result.dart';

void main() {
  group('Deal.fromJson', () {
    test('parses a full fixed-price deal', () {
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd1',
        'title': 'Website relaunch',
        'value_type': 'fixed',
        // The API sends money as a decimal string, not a number.
        'fixed_value': '12500.00',
        'expected_value': '12500.00',
        'is_open_ended': false,
        'currency': 'EUR',
        'stage': 'proposal',
        'expected_close_date': '2026-11-30',
        'probability': 60,
        'notes': 'Waiting on sign-off.',
        'contact_id': 'c1',
        'contact_name': 'Ada Lovelace',
        'organization_id': 'o1',
        'organization_name': 'ACME',
        'is_open': true,
        'created_at': '2026-08-31T09:00:00',
        'updated_at': '2026-08-31T09:00:00',
      });

      expect(deal.title, 'Website relaunch');
      expect(deal.valueType, DealValueType.fixed);
      expect(deal.fixedValue, '12500.00');
      expect(deal.stage, DealStage.proposal);
      expect(deal.expectedCloseDate, DateTime(2026, 11, 30));
      expect(deal.probability, 60);
      // Denormalised, so a list row needs no request per deal.
      expect(deal.contactName, 'Ada Lovelace');
      expect(deal.organizationName, 'ACME');
      expect(deal.isOpen, isTrue);
      expect(deal.formattedExpectedValue, '12,500.00 EUR');
      expect(deal.valueSummary, '12,500.00 EUR');
    });

    test('a bare deal starts open at the top of the pipeline', () {
      final deal = Deal.fromJson(<String, dynamic>{'id': 'd2', 'title': 'Enquiry'});

      expect(deal.stage, DealStage.lead);
      expect(deal.valueType, DealValueType.fixed);
      expect(deal.currency, 'EUR');
      expect(deal.isOpen, isTrue);
      expect(deal.isActive, isTrue);
      expect(deal.isWon, isFalse);
      expect(deal.expectedValue, isNull);
      expect(deal.valueSummary, isNull);
      expect(deal.closedAt, isNull);
    });

    test('a rate-based deal with an estimate carries its derived total', () {
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd3',
        'title': 'Platform work',
        'value_type': 'rate_based',
        'rate': '800.00',
        'rate_unit': 'day',
        'estimated_volume': '60.00',
        'volume_unit': 'day',
        'expected_value': '48000.00',
        'is_open_ended': false,
      });

      expect(deal.valueType, DealValueType.rateBased);
      expect(deal.rateUnit, RateUnit.day);
      expect(deal.formattedRate, '800.00 EUR/day');
      expect(deal.formattedExpectedValue, '48,000.00 EUR');
      // The total is what a list row shows when there is one.
      expect(deal.valueSummary, '48,000.00 EUR');
      expect(deal.isOpenEnded, isFalse);
    });

    test('an open-ended engagement shows its rate rather than nothing', () {
      // The case a single value column could not express. Blanking it would
      // make a real deal at a known day rate look like an unpriced one.
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd4',
        'title': 'Ongoing platform work',
        'value_type': 'rate_based',
        'rate': '800.00',
        'rate_unit': 'day',
        'estimated_volume': null,
        'volume_unit': null,
        'expected_value': null,
        'is_open_ended': true,
      });

      expect(deal.expectedValue, isNull);
      expect(deal.isOpenEnded, isTrue);
      expect(deal.formattedExpectedValue, isNull);
      expect(deal.valueSummary, '800.00 EUR/day · open-ended');
    });

    test('mismatched units mean no total, but not open-ended', () {
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd5',
        'title': 'Six months of something',
        'value_type': 'rate_based',
        'rate': '800.00',
        'rate_unit': 'day',
        'estimated_volume': '6.00',
        'volume_unit': 'month',
        'expected_value': null,
        'is_open_ended': false,
      });

      expect(deal.formattedExpectedValue, isNull);
      expect(deal.isOpenEnded, isFalse);
      // It is estimated, so the summary is the rate without the open-ended note.
      expect(deal.valueSummary, '800.00 EUR/day');
    });

    test('a retainer is priced per month', () {
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd6',
        'title': 'Support retainer',
        'value_type': 'retainer',
        'rate': '2000.00',
        'rate_unit': 'month',
        'expected_value': '24000.00',
      });

      expect(deal.valueType, DealValueType.retainer);
      expect(deal.formattedRate, '2,000.00 EUR/month');
      expect(deal.formattedExpectedValue, '24,000.00 EUR');
    });

    test('a running deal is won, still active, and not open', () {
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd7',
        'title': 'Retainer',
        'stage': 'running',
        'probability': 100,
        'closed_at': '2026-08-30T14:05:00',
      });

      expect(deal.stage, DealStage.running);
      expect(deal.isWon, isTrue);
      // Winning starts the work; it must not drop off the board.
      expect(deal.isActive, isTrue);
      expect(deal.isOpen, isFalse);
      expect(deal.closedAt, isNotNull);
    });

    test('a completed deal is won but off the board', () {
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd8',
        'title': 'Done',
        'stage': 'completed',
      });

      expect(deal.isWon, isTrue);
      expect(deal.isActive, isFalse);
      expect(deal.isOpen, isFalse);
    });

    test('a lost deal keeps its reason', () {
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd9',
        'title': 'Rebrand',
        'stage': 'lost',
        'lost_reason': 'Went with a cheaper agency',
      });

      expect(deal.stage, DealStage.lost);
      expect(deal.isWon, isFalse);
      expect(deal.isActive, isFalse);
      expect(deal.lostReason, 'Went with a cheaper agency');
    });

    test('a stage or unit this build does not know falls back instead of throwing', () {
      // A backend that learns a new stage must not blank the whole screen.
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd10',
        'title': 'Mystery',
        'stage': 'haggling',
        'value_type': 'guesswork',
        'rate_unit': 'fortnight',
      });

      expect(deal.stage, DealStage.lead);
      expect(deal.valueType, DealValueType.fixed);
      expect(deal.rateUnit, isNull);
    });

    test('a numeric amount is accepted as well as a string', () {
      // Defensive: nothing should send one, but a serialiser change must not
      // take the screen down.
      final deal = Deal.fromJson(<String, dynamic>{
        'id': 'd11',
        'title': 'Audit',
        'fixed_value': 750,
        'expected_value': 750,
      });

      expect(deal.fixedValue, '750');
      expect(deal.formattedExpectedValue, '750.00 EUR');
    });

    test('a page of deals keeps the total for the pagination bar', () {
      final page = PagedResult.fromJson(<String, dynamic>{
        'items': <dynamic>[
          <String, dynamic>{'id': 'd1', 'title': 'One', 'stage': 'lead'},
          <String, dynamic>{'id': 'd2', 'title': 'Two', 'stage': 'running'},
        ],
        'total': 7,
        'skip': 0,
        'limit': 2,
      }, Deal.fromJson);

      expect(page.items.map((d) => d.title), ['One', 'Two']);
      expect(page.total, 7);
      expect(page.hasNext, isTrue);
      expect(page.pageCount, 4);
    });
  });

  group('DealStage', () {
    test('only the first four are still being competed for', () {
      for (final stage in [
        DealStage.lead,
        DealStage.qualified,
        DealStage.proposal,
        DealStage.negotiation,
      ]) {
        expect(stage.isOpen, isTrue, reason: '${stage.wire} should be open');
        expect(stage.isWon, isFalse);
        expect(stage.isActive, isTrue);
      }
    });

    test('won, running and completed all count as won', () {
      for (final stage in [DealStage.won, DealStage.running, DealStage.completed]) {
        expect(stage.isWon, isTrue, reason: '${stage.wire} should be won');
        expect(stage.isOpen, isFalse);
      }
    });

    test('only completed and lost leave the board', () {
      expect(DealStage.won.isActive, isTrue);
      expect(DealStage.running.isActive, isTrue);
      expect(DealStage.completed.isActive, isFalse);
      expect(DealStage.lost.isActive, isFalse);
    });

    test('the wire value is what the API uses, not the label', () {
      // Renaming what the operator reads must never change what is stored.
      expect(DealStage.negotiation.wire, 'negotiation');
      expect(DealStage.fromWire('running'), DealStage.running);
      expect(DealStage.fromWire(null), DealStage.lead);
      expect(DealValueType.rateBased.wire, 'rate_based');
      expect(DealStatus.active.wire, 'active');
    });
  });

  group('formatMoney', () {
    test('groups thousands and keeps two decimals', () {
      expect(formatMoney('12500.00', 'EUR'), '12,500.00 EUR');
      expect(formatMoney('999999999999.99', 'EUR'), '999,999,999,999.99 EUR');
      expect(formatMoney('999.99', 'USD'), '999.99 USD');
      expect(formatMoney('1000.00', 'CHF'), '1,000.00 CHF');
    });

    test('does not lose the precision a double would', () {
      // 0.10 is exactly what the API sent; it never went through a binary
      // double, so it comes back out unchanged.
      expect(formatMoney('0.10', 'EUR'), '0.10 EUR');
      expect(formatMoney('0.01', 'EUR'), '0.01 EUR');
    });

    test('pads a short or missing fraction', () {
      expect(formatMoney('5.5', 'EUR'), '5.50 EUR');
      expect(formatMoney('5', 'EUR'), '5.00 EUR');
    });

    test('shows an unrecognised amount verbatim rather than mangling it', () {
      expect(formatMoney('twelve', 'EUR'), 'twelve EUR');
    });
  });
}
