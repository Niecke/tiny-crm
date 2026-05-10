import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/task.dart';
import '../repositories/tasks_repository.dart';

final tasksRepositoryProvider = Provider<TasksRepository>((ref) {
  return TasksRepository(dio);
});

typedef TasksFilter = ({String search, bool includeDone});

final tasksProvider = FutureProvider.family<List<Task>, TasksFilter>((ref, filter) {
  return ref.read(tasksRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        includeDone: filter.includeDone,
      );
});
