/// One slice of a list endpoint, plus the size of the whole result set.
///
/// [total] is what lets the UI say "1–50 of 213" and offer the rest. Without it
/// a full page and the last page look the same, so the list just stops.
class PagedResult<T> {
  const PagedResult({
    required this.items,
    required this.total,
    required this.skip,
    required this.limit,
  });

  final List<T> items;
  final int total;
  final int skip;
  final int limit;

  factory PagedResult.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) fromItem,
  ) {
    return PagedResult(
      items: (json['items'] as List<dynamic>)
          .map((e) => fromItem(e as Map<String, dynamic>))
          .toList(),
      total: json['total'] as int,
      skip: json['skip'] as int,
      limit: json['limit'] as int,
    );
  }

  /// Number of the page currently shown, 1-based.
  int get pageNumber => limit == 0 ? 1 : (skip ~/ limit) + 1;

  /// How many pages the full result set spans, at least 1.
  int get pageCount => limit == 0 ? 1 : ((total + limit - 1) ~/ limit).clamp(1, 1 << 31);

  bool get hasPrevious => skip > 0;
  bool get hasNext => skip + items.length < total;

  /// 1-based index of the first and last item shown, for "x–y of z".
  int get firstIndex => items.isEmpty ? 0 : skip + 1;
  int get lastIndex => skip + items.length;
}

/// Rows requested per page. One value everywhere so paging feels the same on
/// every list; the backend caps `limit` at 200.
const int kPageSize = 25;
