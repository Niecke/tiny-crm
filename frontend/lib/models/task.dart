class Task {
  const Task({
    required this.id,
    required this.title,
    this.description,
    this.dueDate,
    required this.priority,
    this.tags = const [],
  });

  final String id;
  final String title;
  final String? description;
  final DateTime? dueDate;
  final int priority;
  final List<String> tags;

  bool get isOverdue =>
      dueDate != null && dueDate!.isBefore(DateTime.now());

  factory Task.fromJson(Map<String, dynamic> json) => Task(
        id: json['id'] as String,
        title: json['title'] as String,
        description: json['description'] as String?,
        dueDate: json['due_date'] == null
            ? null
            : DateTime.parse(json['due_date'] as String),
        priority: json['priority'] as int,
        tags: (json['tags'] as List<dynamic>?)?.cast<String>() ?? [],
      );
}
