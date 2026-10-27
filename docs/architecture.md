# 架构设计

> 状态：骨架阶段，随开发推进持续更新。

## 1. 端的角色划分

| 端 | 技术 | 职责 |
|----|------|------|
| Windows 桌面端 | Flutter | 完整功能 UI，本地缓存，同步到服务端 |
| Android 端 | Flutter | 与 Windows 端共用一套 Flutter 代码库 |
| 手环端 | Vela 快应用 (JS) | 轻量工具（计算器等），低功耗、小屏交互 |
| 服务端 | Go + Gin + SQLite | 云同步、教务抓取（内网/WebVPN）、第三方数据代理 |

## 2. 业务模块

- **jwgl（教务）**：服务端持有教务账号会话，登录 `jwgl.zqu.edu.cn`（校内直连 / 校外走深信服 WebVPN，参考 ShiGuangSchedule ZQU 适配器的解析逻辑），抓取课表/成绩后转为统一 JSON 下发。
- **sync（云同步）**：各端本地 SQLite（手环端为本地存储），通过服务端做按实体类型的增量同步（后续可引入 `updated_at` + 版本号/逻辑时钟）。
- **express / dorm / library**：均为服务端代理抓取 + 标准化 API。
- **auth**：单用户/多账号待定，先预留 Token 认证中间件位置。

## 3. 目录约定

```
server/
├── cmd/server/        # main 入口
├── internal/
│   ├── api/           # Gin 路由与 handler
│   ├── auth/          # 认证
│   ├── sync/          # 同步引擎
│   ├── jwgl/          # 教务抓取
│   ├── express/       # 快递
│   ├── dorm/          # 宿舍水电
│   ├── library/       # 资源库
│   └── store/         # 存储层（SQLite）
├── config/            # 配置样例
└── start.bat          # 双击启动
```

## 4. API 风格（草案）

- REST + JSON，前缀 `/api/v1`。
- 统一响应包装：`{ "code": 0, "msg": "ok", "data": ... }`。
- 模块示例：
  - `GET /api/v1/timetable?week=8`
  - `POST /api/v1/sync/push` / `GET /api/v1/sync/pull?since=...`
  - `GET /api/v1/express/list`
