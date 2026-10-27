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

## 开发规范（重要）

- **每个会话的操作必须新建一个分支，写完代码后提交 PR**：
  `git checkout -b feat/<日期>-<主题>` → 提交 → push → `gh pr create`，由人工 review 后合并。
- Windows/Android 端 UI 风格参考：[jiushuang/flutter_beautiful_ui](https://github.com/jiushuang/flutter_beautiful_ui)。
- Vela 快应用使用官方 [AIoT-IDE](https://iot.mi.com/vela/quickapp/zh/guide/start/use-ide.html) 开发调试。
