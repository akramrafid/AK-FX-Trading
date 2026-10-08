import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ak_forex_app/main.dart';
import 'package:ak_forex_app/widgets/account_connect_dialog.dart';

void main() {
  testWidgets('Clicking MT4 account tag opens AccountConnectDialog smoothly', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(const AKForexApp());
    await tester.pump();

    // Verify MT4 tag exists and tap it to open AccountConnectDialog
    final accountTag = find.textContaining('#70702138');
    expect(accountTag, findsWidgets);

    await tester.tap(accountTag.first);
    await tester.pumpAndSettle();

    // Verify dialog opened
    expect(find.byType(AccountConnectDialog), findsOneWidget);
    expect(find.text('Connect MT4 Account'), findsOneWidget);
    expect(find.text('ACCOUNT LOGIN / NUMBER'), findsOneWidget);
    expect(find.text('TRADER PASSWORD'), findsOneWidget);
    expect(find.text('BROKER SERVER'), findsOneWidget);
    expect(find.text('Launch MT4 & Auto-Sync Bridge'), findsOneWidget);
    expect(find.text('Connect & Sync MT4'), findsOneWidget);

    // Verify quick select chips work
    expect(find.text('Exness-Real'), findsOneWidget);
    await tester.tap(find.text('Exness-Real'));
    await tester.pump();

    // Close dialog
    final closeBtn = find.byIcon(Icons.close_rounded);
    expect(closeBtn, findsOneWidget);
    await tester.tap(closeBtn);
    await tester.pumpAndSettle();

    expect(find.byType(AccountConnectDialog), findsNothing);
  });
}
