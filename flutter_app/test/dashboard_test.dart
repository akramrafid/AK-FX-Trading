import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ak_forex_app/main.dart';
import 'package:ak_forex_app/widgets/header_nav.dart';
import 'package:ak_forex_app/widgets/market_chips.dart';
import 'package:ak_forex_app/widgets/account_card.dart';
import 'package:ak_forex_app/widgets/risk_meter_card.dart';
import 'package:ak_forex_app/widgets/transactions_table.dart';
import 'package:ak_forex_app/widgets/trading_chart.dart';

void main() {
  testWidgets('Dashboard renders all core components cleanly', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1600, 1000);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(const AKForexApp());

    // Verify HeaderNav
    expect(find.byType(HeaderNav), findsOneWidget);
    expect(find.text('QUANT TRADING DESK'), findsOneWidget);
    expect(find.text('USDCADm'), findsWidgets);

    // Verify MarketChips
    expect(find.byType(MarketChips), findsOneWidget);
    expect(find.text('USDCADm'), findsWidgets);

    // Verify TradingChart
    expect(find.byType(TradingChart), findsOneWidget);
    expect(find.text('1:5 R:R (BE @ 2R)'), findsOneWidget);

    // Verify TransactionsTable
    expect(find.byType(TransactionsTable), findsOneWidget);
    expect(find.text('Open Positions'), findsOneWidget);

    // Verify AccountCard
    expect(find.byType(AccountCard), findsOneWidget);
    expect(find.text('Trading Account'), findsOneWidget);
    expect(find.text('Start Live Trading'), findsOneWidget);
    expect(find.text('Emergency Kill-Switch'), findsOneWidget);

    // Verify RiskMeterCard
    expect(find.byType(RiskMeterCard), findsOneWidget);
    expect(find.text('Risk Guardrails & Health'), findsOneWidget);
    expect(find.text('DAY CEILINGS'), findsOneWidget);
  });
}
