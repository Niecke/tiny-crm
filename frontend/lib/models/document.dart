class Document {
  const Document({
    required this.id,
    required this.title,
    this.description,
    required this.tags,
    required this.format,
    required this.size,
    required this.storageKey,
    required this.hasPreview,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String title;
  final String? description;
  final List<String> tags;
  final String format;
  final int size;
  final String storageKey;
  final bool hasPreview;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory Document.fromJson(Map<String, dynamic> json) => Document(
        id: json['id'] as String,
        title: json['title'] as String,
        description: json['description'] as String?,
        tags: (json['tags'] as List<dynamic>).cast<String>(),
        format: json['format'] as String,
        size: json['size'] as int,
        storageKey: json['storage_key'] as String,
        hasPreview: json['has_preview'] as bool? ?? false,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
