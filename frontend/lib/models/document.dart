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
    this.contactIds = const [],
    this.organizationIds = const [],
    this.dealIds = const [],
    this.projectIds = const [],
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

  // What the document is filed against. A signed contract belongs to a deal,
  // an NDA to the person *and* the company — so these are lists, and the same
  // file can sit under several records without being uploaded twice.
  final List<String> contactIds;
  final List<String> organizationIds;
  final List<String> dealIds;
  final List<String> projectIds;

  /// How many records this document is filed against, all kinds together.
  int get linkCount =>
      contactIds.length +
      organizationIds.length +
      dealIds.length +
      projectIds.length;

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
        contactIds: (json['contact_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        organizationIds:
            (json['organization_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        dealIds: (json['deal_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        projectIds: (json['project_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
