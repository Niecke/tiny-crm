enum ProjectStatus { upcoming, active, completed }

ProjectStatus statusOf(Project p) {
  final now = DateTime.now();
  if (p.endDate != null && p.endDate!.isBefore(now)) return ProjectStatus.completed;
  if (p.startDate.isAfter(now)) return ProjectStatus.upcoming;
  return ProjectStatus.active;
}

class Project {
  const Project({
    required this.id,
    required this.name,
    this.description,
    required this.startDate,
    this.endDate,
    this.contactIds = const [],
    this.taskIds = const [],
    this.documentIds = const [],
  });

  final String id;
  final String name;
  final String? description;
  final DateTime startDate;
  final DateTime? endDate;
  final List<String> contactIds;
  final List<String> taskIds;
  final List<String> documentIds;

  factory Project.fromJson(Map<String, dynamic> json) => Project(
        id: json['id'] as String,
        name: json['name'] as String,
        description: json['description'] as String?,
        startDate: DateTime.parse(json['start_date'] as String),
        endDate: json['end_date'] == null
            ? null
            : DateTime.parse(json['end_date'] as String),
        contactIds: (json['contact_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        taskIds: (json['task_ids'] as List<dynamic>?)?.cast<String>() ?? [],
        documentIds: (json['document_ids'] as List<dynamic>?)?.cast<String>() ?? [],
      );
}
