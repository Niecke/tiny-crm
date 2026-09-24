import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/capture.dart';
import '../models/paged_result.dart';
import '../repositories/captures_repository.dart';

final capturesRepositoryProvider = Provider<CapturesRepository>((ref) {
  return CapturesRepository(dio);
});

/// `status: null` is every status — what the inbox shows under "All".
typedef CapturesFilter = ({CaptureStatus? status, String search, int skip});

/// Keyed by the whole filter — records compare by value, so two widgets asking
/// for the same page share one request. Callers must reset `skip` to 0 whenever
/// anything else in the filter changes.
final capturesProvider = FutureProvider.family<PagedResult<Capture>, CapturesFilter>((
  ref,
  filter,
) {
  return ref
      .read(capturesRepositoryProvider)
      .list(
        status: filter.status,
        search: filter.search.isEmpty ? null : filter.search,
        skip: filter.skip,
      );
});

/// How many captures are waiting — the badge on the nav item, so a backlog is
/// visible without opening the screen. An inbox nobody looks at is the failure
/// mode this whole feature exists to avoid.
final newCaptureCountProvider = FutureProvider<CaptureCount>((ref) {
  return ref.read(capturesRepositoryProvider).count();
});
