import 'package:flutter/material.dart';

import 'api/api_client.dart';
import 'pages/login_page.dart';
import 'pages/timetable_page.dart';

void main() {
  runApp(const ZQUHelperApp());
}

class ZQUHelperApp extends StatelessWidget {
  const ZQUHelperApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ZQUHelper',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF4F6EF7),
        useMaterial3: true,
        fontFamily: 'Microsoft YaHei',
      ),
      home: const HomePage(),
    );
  }
}

/// 启动时按本地保存的 Token 决定进登录页还是课表页。
class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  bool _loading = true;
  bool _hasToken = false;

  @override
  void initState() {
    super.initState();
    ApiClient.loadSaved().then((_) {
      setState(() {
        _hasToken = ApiClient.token != null;
        _loading = false;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return _hasToken ? const TimetablePage() : const LoginPage();
  }
}
