import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// 服务端 API 客户端。统一处理 {code, msg, data} 包装与 Bearer Token。
class ApiClient {
  ApiClient._();

  static String baseUrl = '';
  static String? token;

  static const _prefsKeyBase = 'server_base_url';
  static const _prefsKeyToken = 'server_token';

  /// 从本地恢复上次的地址与 Token。
  static Future<void> loadSaved() async {
    final sp = await SharedPreferences.getInstance();
    baseUrl = sp.getString(_prefsKeyBase) ?? '';
    token = sp.getString(_prefsKeyToken);
  }

  static Future<void> save(String url, String newToken) async {
    baseUrl = url;
    token = newToken;
    final sp = await SharedPreferences.getInstance();
    await sp.setString(_prefsKeyBase, url);
    await sp.setString(_prefsKeyToken, newToken);
  }

  static Future<void> clear() async {
    token = null;
    final sp = await SharedPreferences.getInstance();
    await sp.remove(_prefsKeyToken);
  }

  static Map<String, String> get _headers => {
        'Content-Type': 'application/json; charset=utf-8',
        if (token != null) 'Authorization': 'Bearer $token',
      };

  /// 抛 [ApiException] 便于页面直接展示 msg。
  static Future<dynamic> _request(
    String method,
    String path,
    Map<String, dynamic>? body,
  ) async {
    assert(baseUrl.isNotEmpty, '请先配置服务端地址');
    final uri = Uri.parse('$baseUrl/api/v1$path');
    try {
      final resp = await (method == 'GET'
              ? http.get(uri, headers: _headers)
              : http.post(uri, headers: _headers, body: jsonEncode(body ?? {})))
          .timeout(const Duration(seconds: 15));
      final map = jsonDecode(utf8.decode(resp.bodyBytes)) as Map<String, dynamic>;
      if (resp.statusCode != 200 || (map['code'] as num? ?? -1) != 0) {
        if (resp.statusCode == 401) {
          await clear();
        }
        throw ApiException(map['msg']?.toString() ?? '请求失败(${resp.statusCode})');
      }
      return map['data'];
    } on TimeoutException {
      throw ApiException('请求超时，请检查与服务端的网络连接');
    } on http.ClientException catch (e) {
      throw ApiException('无法连接服务端: ${e.message}');
    }
  }

  /// 登录，成功后保存 Token。
  static Future<void> login(String url, String username, String password) async {
    final clean = url.endsWith('/') ? url.substring(0, url.length - 1) : url;
    baseUrl = clean; // _request 依赖 baseUrl 拼接
    final data = await _request('POST', '/auth/login', {
      'username': username,
      'password': password,
    }) as Map<String, dynamic>;
    await save(clean, data['token'] as String);
  }

  /// 课表数据。term 为空返回最近缓存学期；week 为空返回整学期。
  static Future<Map<String, dynamic>> fetchTimetable({String? term, int? week}) async {
    final q = <String>[
      if (term != null && term.isNotEmpty) 'term=$term',
      if (week != null) 'week=$week',
    ].join('&');
    final data =
        await _request('GET', '/timetable${q.isEmpty ? '' : '?$q'}', null) as Map<String, dynamic>;
    return data;
  }

  /// 触发服务端刷新（异步任务，用 fetchStatus 轮询）。
  static Future<void> refreshTimetable({String? term}) =>
      _request('POST', '/timetable/refresh', {if (term != null) 'term': term});

  /// 抓取任务状态。
  static Future<Map<String, dynamic>> fetchStatus() async =>
      await _request('GET', '/timetable/status', null) as Map<String, dynamic>;
}

class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}
