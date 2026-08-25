import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/paged_result.dart';
import '../models/project.dart';
import '../repositories/projects_repository.dart';

final projectsRepositoryProvider = Provider<ProjectsRepository>((ref) {
  return ProjectsRepository(dio);
});

typedef ProjectsFilter = ({String search, int skip});

final projectsProvider =
    FutureProvider.family<PagedResult<Project>, ProjectsFilter>((ref, filter) {
  return ref.read(projectsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        skip: filter.skip,
      );
});
