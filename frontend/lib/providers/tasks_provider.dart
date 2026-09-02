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

/// Tasks about one record — what a contact or deal detail screen lists.
///
/// Separate family from [tasksProvider] so the dashboard's own search and
/// paging state cannot collide with a detail screen's.
typedef LinkedTasksFilter = ({
  String? contactId,
  String? dealId,
  String? interactionId,
  bool includeDone,
  int skip,
});

final linkedTasksProvider =
    FutureProvider.family<PagedResult<Task>, LinkedTasksFilter>((ref, filter) {
  return ref.read(tasksRepositoryProvider).list(
        contactId: filter.contactId,
        dealId: filter.dealId,
        interactionId: filter.interactionId,
        includeDone: filter.includeDone,
        skip: filter.skip,
      );
});

/// Every task including done ones, for the project link picker.
final allTasksProvider = FutureProvider<List<Task>>((ref) {
  return ref.read(tasksRepositoryProvider).listAll();
});
