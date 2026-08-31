class Contact {
  const Contact({
    required this.id,
    required this.name,
    this.organizationId,
    this.organizationName,
    this.email,
    this.phone,
    this.address,
    required this.tags,
    this.notes,
  });

  final String id;
  final String name;

  /// The company this contact belongs to, or null for someone unaffiliated.
  final String? organizationId;

  /// Read-only: the API sends the linked company's name alongside its id, so a
  /// list can show it without a second request. Writes go through
  /// [organizationId].
  final String? organizationName;
  final String? email;
  final String? phone;
  final String? address;
  final List<String> tags;
  final String? notes;

  factory Contact.fromJson(Map<String, dynamic> json) => Contact(
        id: json['id'] as String,
        name: json['name'] as String,
        organizationId: json['organization_id'] as String?,
        organizationName: json['organization_name'] as String?,
        email: json['email'] as String?,
        phone: json['phone'] as String?,
        address: json['address'] as String?,
        tags: (json['tags'] as List<dynamic>).cast<String>(),
        notes: json['notes'] as String?,
      );
}
