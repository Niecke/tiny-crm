class Contact {
  const Contact({
    required this.id,
    required this.name,
    this.company,
    this.email,
    this.phone,
    this.address,
    required this.tags,
    this.notes,
  });

  final int id;
  final String name;
  final String? company;
  final String? email;
  final String? phone;
  final String? address;
  final List<String> tags;
  final String? notes;

  factory Contact.fromJson(Map<String, dynamic> json) => Contact(
        id: json['id'] as int,
        name: json['name'] as String,
        company: json['company'] as String?,
        email: json['email'] as String?,
        phone: json['phone'] as String?,
        address: json['address'] as String?,
        tags: (json['tags'] as List<dynamic>).cast<String>(),
        notes: json['notes'] as String?,
      );
}
