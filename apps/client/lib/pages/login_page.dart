import 'package:flutter/material.dart';

import '../api/api_client.dart';
import 'timetable_page.dart';

/// 登录页：服务端地址 + 服务端账号密码。
class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _url = TextEditingController();
  final _user = TextEditingController();
  final _pass = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _url.text = ApiClient.baseUrl;
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ApiClient.login(_url.text.trim(), _user.text.trim(), _pass.text);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const TimetablePage()),
      );
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF4F6EF7), Color(0xFF7B5CF0)],
          ),
        ),
        child: Center(
          child: Card(
            elevation: 8,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            child: Container(
              width: 380,
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('ZQUHelper',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text('肇庆学院校园助手',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: theme.colorScheme.outline)),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _url,
                    decoration: const InputDecoration(
                      labelText: '服务端地址',
                      hintText: 'http://192.168.1.10:8787',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.dns_outlined),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _user,
                    decoration: const InputDecoration(
                      labelText: '账号',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.person_outline),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _pass,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: '密码',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.lock_outline),
                    ),
                    onSubmitted: (_) => _submit(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 10),
                    Text(_error!,
                        style: TextStyle(color: theme.colorScheme.error)),
                  ],
                  const SizedBox(height: 18),
                  FilledButton(
                    onPressed: _busy ? null : _submit,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 10),
                      child: _busy
                          ? const SizedBox(
                              width: 20, height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Text('登录'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
