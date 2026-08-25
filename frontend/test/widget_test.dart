@TestOn('browser')
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';

// main.dart reaches dart:js_interop through the version check, so this file
// only compiles for the web target — `flutter test` on the VM skips it, and
// `flutter test --platform chrome` runs it.
void main() {
  testWidgets('App renders without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: App()));
    await tester.pump();
  });
}
