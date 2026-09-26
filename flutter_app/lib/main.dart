import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'providers/trading_provider.dart';
import 'screens/dashboard_screen.dart';
import 'services/api_service.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AKForexApp());
}

class AKForexApp extends StatelessWidget {
  final TradingProvider? provider;

  const AKForexApp({super.key, this.provider});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => provider ?? TradingProvider(
            api: ApiService(
              baseUrl: 'http://127.0.0.1:8642',
              wsUrl: 'ws://127.0.0.1:8642/ws',
            ),
          ),
        ),
      ],
      child: MaterialApp(
        title: 'AK Forex Trading Desk',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.darkTheme,
        home: const DashboardScreen(),
      ),
    );
  }
}
