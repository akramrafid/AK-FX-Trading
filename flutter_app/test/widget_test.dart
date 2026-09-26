import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ak_forex_app/main.dart';

void main() {
  testWidgets('AKForexApp builds without crashing', (WidgetTester tester) async {
    // Set standard desktop viewport for testing
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(const AKForexApp());
    expect(find.byType(AKForexApp), findsOneWidget);
  });
}
