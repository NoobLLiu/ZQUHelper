# ZQUHelper 服务端（Go + Gin）

云同步 + 教务数据抓取服务。双击 `start.bat` 启动。

> 状态：**课程表模块已实现**（抓取 worker + SQLite 缓存 + REST API）。

## 模块

| 目录 | 职责 |
|------|------|
| `cmd/server` | 入口：读配置 → 开 SQLite → 挂路由 |
| `internal/api` | Gin 路由（`/api/v1`，统一 `{code, msg, data}` 包装） |
| `internal/auth` | 单用户 Token 认证（账号密码来自 config.yaml） |
| `internal/sync` | 多端数据云同步（未实现） |
| `internal/jwgl` | 课表：调度 Python worker 抓取 → 缓存 → 下发 |
| `internal/express` | 快递查询（未实现） |
| `internal/dorm` | 宿舍水电（未实现） |
| `internal/library` | 自建资源库（未实现） |
| `internal/store` | SQLite 存储层（modernc.org/sqlite 纯 Go，免 CGO） |
| `tools/zqu_fetch` | 课表抓取 Python worker（Playwright + ddddocr，肇庆学院专用） |

## 课表抓取架构

WebVPN 滑块破解与验证码 OCR 依赖真实浏览器，无法用纯 HTTP 在 Go 里重写，
因此采用「**Go 编排 + Python worker 子进程**」：

```
客户端 → POST /api/v1/timetable/refresh
       → Go 起 python fetch_worker.py（mode=auto：先校内直连探测，失败走 WebVPN）
       → worker 用 Playwright 登录教务 → 单请求取整学期课表 JSON → 写临时文件
       → Go 读回结果 → 存 SQLite → 客户端 GET /api/v1/timetable 读取
```

worker 依赖 Python 环境：`playwright`、`ddddocr`、`opencv-python`（本机 venv 已装齐，
路径见 config.example.yaml 注释）。

## API（/api/v1，除 ping/login 外均需 Bearer Token）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/ping` | 存活探测 |
| POST | `/auth/login` | `{username,password}` → `{token}` |
| GET | `/timetable?term=&week=` | 读课表缓存（省略 term 取最近学期，week 过滤某周） |
| GET | `/timetable/terms` | 已缓存学期列表 |
| POST | `/timetable/refresh` | 触发抓取（异步，同一时间只允许一个任务） |
| GET | `/timetable/status` | 抓取任务状态 |

## 启动

1. 配置：复制 `config/config.example.yaml` 为 `config/config.yaml`，
   填 `jwgl.username/password`（教务账号）与 `auth.username/password`（客户端登录用），
   `jwgl.python_path` 建议填已装好依赖的 venv 解释器完整路径。
2. 开发：双击 `start.bat`（内部执行 `go run ./cmd/server`，需 PATH 里有 Go）。
3. 验证：`curl http://127.0.0.1:8787/api/v1/ping`。
