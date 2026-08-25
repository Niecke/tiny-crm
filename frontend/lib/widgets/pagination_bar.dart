import 'package:flutter/material.dart';

import '../models/paged_result.dart';

/// Footer for a paged list: "1–25 of 213" with previous/next controls.
///
/// Shows nothing at all when everything fits on one page, so short lists look
/// exactly as they did before paging existed.
class PaginationBar extends StatelessWidget {
  const PaginationBar({
    super.key,
    required this.page,
    required this.onSkipChanged,
  });

  final PagedResult<dynamic> page;

  /// Called with the new `skip` offset to load.
  final ValueChanged<int> onSkipChanged;

  @override
  Widget build(BuildContext context) {
    if (page.total <= page.items.length && page.skip == 0) {
      return const SizedBox.shrink();
    }

    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            '${page.firstIndex}–${page.lastIndex} of ${page.total}',
            style: theme.textTheme.bodySmall,
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                onPressed: page.hasPrevious
                    ? () => onSkipChanged(
                        (page.skip - page.limit).clamp(0, page.total),
                      )
                    : null,
                icon: const Icon(Icons.chevron_left),
                tooltip: 'Previous page',
                visualDensity: VisualDensity.compact,
              ),
              Text(
                '${page.pageNumber}/${page.pageCount}',
                style: theme.textTheme.bodySmall,
              ),
              IconButton(
                onPressed: page.hasNext
                    ? () => onSkipChanged(page.skip + page.limit)
                    : null,
                icon: const Icon(Icons.chevron_right),
                tooltip: 'Next page',
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
