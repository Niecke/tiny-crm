import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../models/deal.dart';
import '../models/paged_result.dart';
import '../repositories/deals_repository.dart';

final dealsRepositoryProvider = Provider<DealsRepository>((ref) {
  return DealsRepository(dio);
});

/// `stage` narrows to one exact column of the pipeline; `status` asks the
/// coarser question (in play / on my plate / won / finished). Both null means
/// everything.
typedef DealsFilter = ({String search, DealStage? stage, DealStatus? status, int skip});

/// Keyed by the whole filter — records compare by value, so two widgets asking
/// for the same page share one request. Callers must reset `skip` to 0 whenever
/// anything else in the filter changes, or page 3 of the old query is requested
/// for the new one.
final dealsProvider = FutureProvider.family<PagedResult<Deal>, DealsFilter>((ref, filter) {
  return ref.read(dealsRepositoryProvider).list(
        search: filter.search.isEmpty ? null : filter.search,
        stage: filter.stage,
        status: filter.status,
        skip: filter.skip,
      );
});
