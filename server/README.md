# ZQUHelper 服务端（Go + Gin）

云同步 + 教务数据抓取服务。双击 `start.bat` 启动。

> 状态：骨架占位，各业务模块目录已建好，实现随会话推进。

## 模块

| 目录 | 职责 |
|------|------|
| `cmd/server` | 入口 |
| `internal/api` | Gin 路由与 handler |
| `internal/auth` | 认证（Token） |
| `internal/sync` | 多端数据云同步 |
| `internal/jwgl` | 教务系统抓取（课表/成绩，含 WebVPN） |
| `internal/express` | 快递查询 |
| `internal/dorm` | 宿舍水电 |
| `internal/library` | 自建资源库 |
| `internal/store` | SQLite 存储层 |

## 启动

- 开发：双击 `start.bat`（内部执行 `go run ./cmd/server`，需 PATH 里有 Go）。
- 配置：复制 `config/config.example.yaml` 为 `config/config.yaml`（不入库）。

## 依赖

后续引入 Gin 时：`go get github.com/gin-gonic/gin`；存储层计划使用 `modernc.org/sqlite`（纯 Go，免 CGO，Windows 编译省心）。
