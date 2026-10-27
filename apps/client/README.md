# Flutter 客户端（Windows + Android）

一套 Flutter 代码覆盖 Windows 桌面端与 Android 端。

> 状态：**课程表模块已实现**（登录页 + 课表周视图），数据全部来自服务端 API，本端不做教务抓取。

## 模块

- 登录页：填服务端地址 + 服务端账号密码（不是教务账号）。
- 课表页：周视图网格 + 彩色课程卡片，周次切换、手动刷新（触发服务端抓取教务）、点卡片看详情。

## 初始化平台目录

仓库只包含 `pubspec.yaml` 与 `lib/`（平台工程由各机器生成，不入库）。首次使用在本目录执行：

```bash
cd apps/client
flutter create --org com.nooblliu --platforms=windows,android --project-name zqu_helper .
flutter pub get
flutter run -d windows     # 或 -d <android 设备>
```

## 规划（其余模块）

- **UI 风格**：参考 [jiushuang/flutter_beautiful_ui](https://github.com/jiushuang/flutter_beautiful_ui)（纯 Dart 手写组件、注重动效与视觉），首个参考对象为 `saas_dashboard`（仪表盘式首页，适合作为模块入口）。
- **模块入口**：课表（已完成）、快递、宿舍水电、资源库、设置/同步。
- **网络层**：统一 `lib/api/api_client.dart` 对接服务端 `/api/v1`，响应包装 `{code, msg, data}`。
