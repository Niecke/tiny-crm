import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/paged_result.dart';
import '../models/task.dart';
import '../repositories/tasks_repository.dart';

final tasksRepositoryProvider = Provider<TasksRepository>((ref) {
  return TasksRepository(dio);
});

typedef TasksFilter = ({String search, bool includeDone, int skip});

final tasksProvider = FutureProvider.family<PagedResult<Task>, TasksFilter>((ref, filter) {
  return ref.read(tasksRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        includeDone: filter.includeDone,
        skip: filter.skip,
      );
});

/// Every task including done ones, for the project link picker.
final allTasksProvider = FutureProvider<List<Task>>((ref) {
  return ref.read(tasksRepositoryProvider).listAll();
});
