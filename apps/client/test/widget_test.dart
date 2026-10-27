// 冒烟测试：App 能构建且显示登录页（无本地 Token 时）。
//
// 注意：CI 的 flutter create 引导不会覆盖本文件
// （默认模板 widget_test.dart 引用不存在的 MyApp，会导致 analyze 失败）。
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:zqu_helper/main.dart';

void main() {
  testWidgets('App 启动后渲染出首页骨架', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({}); // HomePage 启动时会读本地 Token
    await tester.pumpWidget(const ZQUHelperApp());
    await tester.pump(); // 完成 Token 读取
    await tester.pump(); // 渲染登录页
    // 未保存 Token 时应停在登录页标题
    expect(find.text('ZQUHelper'), findsOneWidget);
  });
}
