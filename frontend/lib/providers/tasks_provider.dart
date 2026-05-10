import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/task.dart';
import '../repositories/tasks_repository.dart';

final tasksRepositoryProvider = Provider<TasksRepository>((ref) {
  return TasksRepository(dio);
});

final tasksProvider = FutureProvider.family<List<Task>, String>((ref, search) {
  return ref.read(tasksRepositoryProvider).list(search: search.isEmpty ? null : search);
});
