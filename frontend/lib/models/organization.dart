/// A company, as a record in its own right.
///
/// Replaces the free-text company field on a contact: one row per company, so
/// "everyone at ACME" is a question with an answer and two spellings are no
/// longer two companies.
class Organization {
  const Organization({
    required this.id,
    required this.name,
    this.domain,
    this.email,
    this.phone,
    this.address,
    this.industry,
    this.notes,
    this.contactCount = 0,
  });

  final String id;
  final String name;
  final String? domain;

  /// The shared mailbox — office@, info@ — rather than a person's own address.
  final String? email;

  /// The switchboard number, for the same reason.
  final String? phone;
  final String? address;
  final String? industry;
  final String? notes;

  /// How many contacts point here. Sent by the API so a list row does not need
  /// a request of its own.
  final int contactCount;

  factory Organization.fromJson(Map<String, dynamic> json) => Organization(
        id: json['id'] as String,
        name: json['name'] as String,
        domain: json['domain'] as String?,
        email: json['email'] as String?,
        phone: json['phone'] as String?,
        address: json['address'] as String?,
        industry: json['industry'] as String?,
        notes: json['notes'] as String?,
        contactCount: json['contact_count'] as int? ?? 0,
      );
}
