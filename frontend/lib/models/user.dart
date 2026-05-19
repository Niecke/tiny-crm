class User {
  const User({
    required this.email,
    this.name,
    this.passwordChangedAt,
  });

  final String email;
  final String? name;
  final DateTime? passwordChangedAt;

  factory User.fromJson(Map<String, dynamic> json) => User(
        email: json['email'] as String,
        name: json['name'] as String?,
        passwordChangedAt: json['password_changed_at'] == null
            ? null
            : DateTime.parse(json['password_changed_at'] as String).toLocal(),
      );
}
