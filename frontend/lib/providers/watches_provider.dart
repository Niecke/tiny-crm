import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/paged_result.dart';
import '../models/watch.dart';
import '../repositories/watches_repository.dart';

final watchesRepositoryProvider = Provider<WatchesRepository>((ref) {
  return WatchesRepository(dio);
});

/// `due: true` is the sweep list — what to work through today. `active: null`
/// includes paused sources.
typedef WatchesFilter = ({
  String search,
  WatchKind? kind,
  bool? due,
  bool? active,
  int skip,
});

/// Keyed by the whole filter — records compare by value, so two widgets asking
/// for the same page share one request. Callers must reset `skip` to 0 whenever
/// anything else in the filter changes.
final watchesProvider =
    FutureProvider.family<PagedResult<Watch>, WatchesFilter>((ref, filter) {
  return ref.read(watchesRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        kind: filter.kind,
        due: filter.due,
        active: filter.active,
        skip: filter.skip,
      );
});

/// How many sources are due right now — the badge on the nav item, so the sweep
/// is visible without opening the screen.
final dueWatchCountProvider = FutureProvider<int>((ref) async {
  // limit 1: only the total is wanted, not the rows.
  final page = await ref
      .read(watchesRepositoryProvider)
      .list(due: true, active: true, limit: 1);
  return page.total;
});

/// One source's sweep history, newest first.
typedef WatchChecksFilter = ({String watchId, int skip});

final watchChecksProvider =
    FutureProvider.family<PagedResult<WatchCheck>, WatchChecksFilter>((ref, filter) {
  return ref.read(watchesRepositoryProvider).checks(filter.watchId, skip: filter.skip);
});
