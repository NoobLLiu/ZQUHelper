# ZQUHelper

肇庆学院校园综合助手：整合教务课表、快递、宿舍水电、自建资源库等学习与生活模块，支持 **Windows / Android / 小米 Vela 手环** 三端，数据云同步。

## 总体架构

```
┌─────────────┐  ┌──────────────┐  ┌─────────────────┐
│ Flutter 客户端│  │ Flutter 客户端 │  │ Vela 快应用(手环) │
│  Windows     │  │  Android     │  │  小米手环 10 NFC │
└──────┬──────┘  └──────┬───────┘  └────────┬────────┘
       │                │                   │
       └────────────────┼───────────────────┘
                        │ HTTPS (REST / JSON)
                 ┌──────▼──────┐
                 │  Go + Gin   │
                 │   服务端     │
                 │  (云同步 +    │
                 │  教务抓取)    │
                 └──────┬──────┘
                        │
              ┌─────────┼──────────┐
              ▼         ▼          ▼
          SQLite     教务系统     第三方数据
          (本地存储)  (WebVPN/内网)  (快递/水电等)
```

- **服务端负责抓取教务数据**（含校外 WebVPN 场景），客户端只调 API，各端不重复实现抓取逻辑。
- 服务端双击 `server/start.bat` 即可启动（需本机装有 Go 或使用编译产物）。

## 目录结构

```
ZQUHelper/
├── apps/
│   ├── client/            # Flutter 客户端（Windows + Android）
│   └── vela/
│       └── calculator/    # Vela 快应用：计算器（小米手环 10 NFC）
├── docs/                  # 架构文档、各端开发指南
├── server/                # Go + Gin 服务端
│   ├── cmd/server/        # 入口
│   ├── internal/          # 业务模块（api/auth/sync/jwgl/express/dorm/library/store）
│   ├── tools/zqu_fetch/   # 课表抓取 Python worker（Playwright，肇庆学院专用）
│   └── start.bat          # 双击启动
└── README.md
```

## 功能模块（规划）

| 模块 | 代码位置 | 说明 |
|------|----------|------|
| 教务课表/成绩 | `server/internal/jwgl` | 服务端登录教务系统抓取（含 WebVPN），下发 JSON |
| 云同步 | `server/internal/sync` | 多端数据同步引擎 |
| 快递 | `server/internal/express` | 快递查询/取件提醒 |
| 宿舍水电 | `server/internal/dorm` | 水电查询与余额提醒 |
| 自建资源库 | `server/internal/library` | 个人资料收集与检索 |
| 认证 | `server/internal/auth` | 账号体系与 Token |
| 手环端工具 | `apps/vela/calculator` | Vela 快应用（首个：计算器） |

## 当前进度

- ✅ **课程表模块（Windows/Android + 服务端）**：服务端由 Go 编排精简版 Python 抓取 worker
  （Playwright 登录教务 + 整学期课表 JSON），结果缓存 SQLite 并经 REST 下发；
  客户端登录页 + 周视图课表页。Vela 手环端暂未做。
- 双端均无公网 IP 的连接方案见 [docs/connectivity.md](docs/connectivity.md)（推荐 Tailscale 组网）。

## 开源致谢

本项目是集锦项目，开发中引入/参考了以下优秀的开源项目（排名不分先后，均未修改其仓库内容）：

- [ShiGuangSchedule/shiguangschedule](https://github.com/ShiGuangSchedule/shiguangschedule) —— 课程表模块的页面布局与交互参考。
- [jiushuang/flutter_beautiful_ui](https://github.com/jiushuang/flutter_beautiful_ui) —— 客户端整体 UI 风格参考。
- 自研课程表抓取脚本（本地 GetTimeTable/zqu-timetable-scraper，已精简为肇庆学院专用 worker 收录于 `server/tools/zqu_fetch/`），其能力依赖：
  - [microsoft/playwright-python](https://github.com/microsoft/playwright-python) —— 真实浏览器自动化（登录、WebVPN 滑块）。
  - [sml2h3/ddddocr](https://github.com/sml2h3/ddddocr) —— 教务图形验证码 OCR。
  - [opencv/opencv-python](https://github.com/opencv/opencv-python) —— 滑块缺口定位与验证码预处理。
- Go 侧依赖：
  - [gin-gonic/gin](https://github.com/gin-gonic/gin) —— Web 框架。
  - [modernc.org/sqlite](https://gitlab.com/cznic/sqlite) —— 纯 Go SQLite 驱动（免 CGO）。
  - [gopkg.in/yaml.v3](https://gopkg.in/yaml.v3) —— 配置解析。

> 感谢以上项目的作者与贡献者。本仓库仅在自己代码中引用与致谢，不会打扰上游。

## 开发规范（重要）

- **每个会话的操作必须新建一个分支，写完代码后提交 PR**：
  `git checkout -b feat/<日期>-<主题>` → 提交 → push → `gh pr create`，由人工 review 后合并。
- Windows/Android 端 UI 风格参考：[jiushuang/flutter_beautiful_ui](https://github.com/jiushuang/flutter_beautiful_ui)。
- Vela 快应用使用官方 [AIoT-IDE](https://iot.mi.com/vela/quickapp/zh/guide/start/use-ide.html) 开发调试。

## CI（GitHub Actions）

`.github/workflows/ci.yml`：**每次提交自动编译全部目标**，产物在该次运行的 Artifacts 里下载：

| Job | 运行环境 | 产物 |
|-----|----------|------|
| `server` | Go（windows runner） | `server-windows`：zquhelper-server.exe |
| `client` | Flutter stable（windows runner） | `client-windows`：Windows 整包 zip；`client-android-apk`：release APK |
| `vela` | Node 22 + AIoT-toolkit 2.0（ubuntu runner） | `vela-calculator-rpk`：手环调试安装包 .rpk |

说明：
- 客户端目前是占位阶段，CI 会先用 `flutter create` 引导生成工程再编译，正式代码落地后移除该步骤。
- rpk 为 debug 包（工具链内置调试签名），发布签名待配置时再启用 `release` 模式。
