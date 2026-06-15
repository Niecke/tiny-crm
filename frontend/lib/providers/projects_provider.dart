import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/project.dart';
import '../repositories/projects_repository.dart';

final projectsRepositoryProvider = Provider<ProjectsRepository>((ref) {
  return ProjectsRepository(dio);
});

final projectsProvider = FutureProvider.family<List<Project>, String>((ref, search) {
  return ref.read(projectsRepositoryProvider).list(search: search.isEmpty ? null : search);
});
