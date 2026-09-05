import '../core/money_text.dart';

/// How far along we are with this party.
///
/// Orthogonal to [RelationType]: status is *how far along we are*, type is
/// *what this party is to me*. Two fields, because collapsing them would lose
/// "partner we have not approached yet" — which is the row worth acting on.
enum LifecycleStatus {
  lead('lead', 'Lead'),
  prospect('prospect', 'Prospect'),
  customer('customer', 'Customer'),
  former('former', 'Former');

  const LifecycleStatus(this.wire, this.label);

  /// The value the API uses. Kept separate from [label] so renaming what the
  /// operator reads never changes what is stored.
  final String wire;
  final String label;

  /// Null for "not set" *and* for a value this build does not know: the column
  /// is nullable anyway, so an older build shows the field as empty rather
  /// than blanking the screen when the backend learns a new status.
  static LifecycleStatus? fromWire(String? value) {
    for (final status in LifecycleStatus.values) {
      if (status.wire == value) return status;
    }
    return null;
  }
}

/// What this party is to me — see [LifecycleStatus] for why both exist.
enum RelationType {
  customer('customer', 'Customer'),
  partner('partner', 'Partner'),

  /// A bigger consultancy that might subcontract work out to me.
  subcontractingTarget('subcontracting_target', 'Subcontracting target'),

  /// The public buyer side of a tender.
  contractingAuthority('contracting_authority', 'Contracting authority');

  const RelationType(this.wire, this.label);

  final String wire;
  final String label;

  static RelationType? fromWire(String? value) {
    for (final type in RelationType.values) {
      if (type.wire == value) return type;
    }
    return null;
  }
}

/// Where they came from. `jobBoard` and `tenderPortal` mirror the watch kinds,
/// because a sweep that turns into a person is how those contacts arrive.
enum ContactSource {
  referral('referral', 'Referral'),
  inbound('inbound', 'Inbound'),
  outbound('outbound', 'Outbound'),
  event('event', 'Event'),
  jobBoard('job_board', 'Job board'),
  tenderPortal('tender_portal', 'Tender portal'),
  other('other', 'Other');

  const ContactSource(this.wire, this.label);

  final String wire;
  final String label;

  static ContactSource? fromWire(String? value) {
    for (final source in ContactSource.values) {
      if (source.wire == value) return source;
    }
    return null;
  }
}

/// Whether this party works with freelancers at all — the single answer that
/// decides whether an approach is worth making.
///
/// Three states, not two. "No" and "never asked" are different answers, and
/// [unknown] is the list that produces the next approach, so it has to be
/// askable — both in the form and in the filter.
enum FreelancerAnswer {
  yes('yes', 'Works with freelancers'),
  no('no', 'Does not use freelancers'),
  unknown('unknown', 'Never asked');

  const FreelancerAnswer(this.wire, this.label);

  final String wire;
  final String label;

  static FreelancerAnswer fromBool(bool? value) => switch (value) {
        true => FreelancerAnswer.yes,
        false => FreelancerAnswer.no,
        null => FreelancerAnswer.unknown,
      };

  /// What the API stores: null for [unknown], which is why the column is
  /// nullable in the first place.
  bool? get asBool => switch (this) {
        FreelancerAnswer.yes => true,
        FreelancerAnswer.no => false,
        FreelancerAnswer.unknown => null,
      };
}

class Contact {
  const Contact({
    required this.id,
    required this.name,
    this.jobTitle,
    this.organizationId,
    this.organizationName,
    this.email,
    this.emailSecondary,
    this.phone,
    this.phoneSecondary,
    this.website,
    this.street,
    this.postalCode,
    this.city,
    this.country,
    this.lifecycleStatus,
    this.relationType,
    this.source,
    this.preferredLanguage,
    this.birthday,
    this.knownDayRate,
    this.rateCurrency,
    this.worksWithFreelancers,
    required this.tags,
    this.notes,
  });

  final String id;
  final String name;

  /// What they do there — "Head of Delivery" and "Werkstudent" are not the
  /// same conversation.
  final String? jobTitle;

  /// The company this contact belongs to, or null for someone unaffiliated.
  final String? organizationId;

  /// Read-only: the API sends the linked company's name alongside its id, so a
  /// list can show it without a second request. Writes go through
  /// [organizationId].
  final String? organizationName;
  final String? email;

  /// The private address and the number that actually gets answered.
  final String? emailSecondary;
  final String? phone;
  final String? phoneSecondary;
  final String? website;

  // --- Where the post goes --------------------------------------------------
  // Four fields rather than one blob, so a letter, an invoice and a vCard can
  // each take the parts they need.
  final String? street;
  final String? postalCode;
  final String? city;

  /// ISO 3166-1 alpha-2, upper-cased by the API.
  final String? country;

  final LifecycleStatus? lifecycleStatus;
  final RelationType? relationType;
  final ContactSource? source;

  /// ISO 639-1, lower-cased by the API — which language to write in.
  final String? preferredLanguage;
  final DateTime? birthday;

  /// The rate as heard, not a quote. The exact decimal string the API sent —
  /// money never goes through a double, see [formatMoney].
  final String? knownDayRate;
  final String? rateCurrency;

  /// Null means never asked, which is not the same answer as false.
  final bool? worksWithFreelancers;

  final List<String> tags;
  final String? notes;

  FreelancerAnswer get freelancerAnswer => FreelancerAnswer.fromBool(worksWithFreelancers);

  /// The address as it would go on an envelope, or null when no part of it is
  /// filled in. Postcode and city share a line, like every European address.
  String? get postalAddress {
    final town = [postalCode, city].where((p) => p != null && p.isNotEmpty).join(' ');
    final lines = [street, town.isEmpty ? null : town, country]
        .where((p) => p != null && p.isNotEmpty)
        .cast<String>();
    return lines.isEmpty ? null : lines.join('\n');
  }

  /// "850.00 EUR/day", or null when no rate has been heard.
  String? get formattedDayRate => (knownDayRate == null || rateCurrency == null)
      ? null
      : '${formatMoney(knownDayRate!, rateCurrency!)}/day';

  factory Contact.fromJson(Map<String, dynamic> json) => Contact(
        id: json['id'] as String,
        name: json['name'] as String,
        jobTitle: json['job_title'] as String?,
        organizationId: json['organization_id'] as String?,
        organizationName: json['organization_name'] as String?,
        email: json['email'] as String?,
        emailSecondary: json['email_secondary'] as String?,
        phone: json['phone'] as String?,
        phoneSecondary: json['phone_secondary'] as String?,
        website: json['website'] as String?,
        street: json['street'] as String?,
        postalCode: json['postal_code'] as String?,
        city: json['city'] as String?,
        country: json['country'] as String?,
        lifecycleStatus: LifecycleStatus.fromWire(json['lifecycle_status'] as String?),
        relationType: RelationType.fromWire(json['relation_type'] as String?),
        source: ContactSource.fromWire(json['source'] as String?),
        preferredLanguage: json['preferred_language'] as String?,
        birthday: json['birthday'] == null ? null : DateTime.parse(json['birthday'] as String),
        // A decimal string; a number is accepted too so a hand-rolled payload
        // cannot break the screen.
        knownDayRate: json['known_day_rate'] == null ? null : '${json['known_day_rate']}',
        rateCurrency: json['rate_currency'] as String?,
        worksWithFreelancers: json['works_with_freelancers'] as bool?,
        tags: (json['tags'] as List<dynamic>? ?? <dynamic>[]).cast<String>(),
        notes: json['notes'] as String?,
      );
}
