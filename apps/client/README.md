# Flutter 客户端（Windows + Android）

一套 Flutter 代码覆盖 Windows 桌面端与 Android 端。

> 状态：骨架占位。后续会话执行 `flutter create` 生成工程后填充。

## 规划

- **UI 风格**：参考 [jiushuang/flutter_beautiful_ui](https://github.com/jiushuang/flutter_beautiful_ui)（纯 Dart 手写组件、注重动效与视觉），首个参考对象为 `saas_dashboard`（仪表盘式首页，适合作为模块入口）。
- **模块入口**：课表、快递、宿舍水电、资源库、设置/同步。
- **网络层**：统一 dio 客户端对接服务端 `/api/v1`。
- **本地存储**：drift/SQLite，配合 `server/internal/sync` 做增量同步。

## 后续初始化命令（到时执行）

```bash
flutter create --org com.nooblliu --platforms=windows,android client
```
